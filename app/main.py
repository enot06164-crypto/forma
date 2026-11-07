"""FORMA — конвертер файлов и студия стикеров. FastAPI-приложение."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import qrcode
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image

import db
import stickers
from convert import ConvertError, convert, probe
from formats import KIND_LABEL, kind_of, mime_of, targets_for

DATA_DIR = os.environ.get("DATA_DIR", "/data")
FILES_DIR = os.path.join(DATA_DIR, "files")
PREVIEW_DIR = os.path.join(DATA_DIR, "previews")
MAX_UPLOAD = int(os.environ.get("MAX_UPLOAD_MB", "200")) * 1024 * 1024
TTL_DAYS = int(os.environ.get("TTL_DAYS", "7"))
PUBLIC_BASE = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
COOKIE = "forma_sid"

os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(PREVIEW_DIR, exist_ok=True)
db.init()

app = FastAPI(title="FORMA", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

EXEC = ThreadPoolExecutor(max_workers=2, thread_name_prefix="conv")
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


# ------------------------------------------------------------------ сессия

@app.middleware("http")
async def session_middleware(request: Request, call_next):
    sid = request.cookies.get(COOKIE)
    fresh = not (sid and re.fullmatch(r"[0-9a-f]{32}", sid))
    if fresh:
        sid = uuid.uuid4().hex
    request.state.sid = sid
    response = await call_next(request)
    if fresh:
        response.set_cookie(COOKIE, sid, max_age=365 * 86400, httponly=True,
                            samesite="lax", path="/")
    return response


def base_url(request: Request) -> str:
    if PUBLIC_BASE:
        return PUBLIC_BASE
    return str(request.base_url).rstrip("/")


# ------------------------------------------------------------------ утилиты

def _image_meta(path: str, ext: str) -> dict:
    if ext == "svg":
        return {}
    try:
        with Image.open(path) as im:
            return {"width": im.width, "height": im.height, "mode": im.mode}
    except Exception:
        return {}


def _file_payload(f: dict, request: Request) -> dict:
    meta = {}
    try:
        meta = json.loads(f.get("meta") or "{}")
    except Exception:
        pass
    return {
        "id": f["id"], "name": f["name"], "ext": f["ext"], "kind": f["kind"],
        "size": f["size"], "role": f["role"], "parent": f["parent"],
        "created": f["created"], "meta": meta,
        "url": f"/f/{f['id']}", "preview": f"/p/{f['id']}",
        "page": f"/d/{f['id']}", "qr": f"/qr/{f['id']}.png",
        "poster": f"/poster/{f['id']}.png" if meta.get("poster") else None,
        "targets": targets_for(f["ext"]) if f["role"] == "source" else [],
    }


def _own(fid: str, sid: str) -> dict:
    f = db.get_file(fid)
    if not f or f["sid"] != sid:
        raise HTTPException(404, "файл не найден")
    return f


# ------------------------------------------------------------------ страницы

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    base = base_url(request)
    return templates.TemplateResponse("index.html", {
        "request": request, "base": base, "stats": db.stats(),
        "kinds": KIND_LABEL, "v": hashlib.md5(base.encode()).hexdigest()[:8],
    }, headers={"Cache-Control": "no-store"})


@app.get("/d/{fid}", response_class=HTMLResponse)
async def download_page(fid: str, request: Request):
    f = db.get_file(fid)
    if not f:
        raise HTTPException(404, "файл не найден или срок хранения истёк")
    payload = _file_payload(f, request)
    text = None
    if f["ext"] in ("txt", "csv", "md", "html", "htm"):
        try:
            with open(f["path"], "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read(4000)
        except Exception:
            text = None
    base = base_url(request)
    return templates.TemplateResponse("download.html", {
        "request": request, "base": base, "f": payload,
        "text": text, "stats": db.stats(),
        "v": hashlib.md5(base.encode()).hexdigest()[:8],
    }, headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ API

@app.post("/api/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    sid = request.state.sid
    name = Path(file.filename or "file").name
    name = re.sub(r"[^\w\s.\-()\[\]]+", "_", name, flags=re.UNICODE)[:120] or "file"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    kind = kind_of(ext)
    if not kind:
        raise HTTPException(415, f"формат .{ext or '?'} не поддерживается")

    fid = uuid.uuid4().hex[:16]
    folder = os.path.join(FILES_DIR, sid)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{fid}.{ext}")

    size = 0
    try:
        with open(path, "wb") as out:
            while True:
                chunk = await file.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, f"файл больше {MAX_UPLOAD // (1024*1024)} МБ")
                out.write(chunk)
    except HTTPException:
        if os.path.exists(path):
            os.unlink(path)
        raise
    if size == 0:
        os.unlink(path)
        raise HTTPException(400, "пустой файл")

    meta = probe(path) if kind in ("audio", "video") else _image_meta(path, ext)
    if ext == "gif":  # у GIF важна длительность — она нужна редактору фрагмента
        meta.update({k: v for k, v in probe(path).items() if v is not None})
    db.add_file(fid, sid, name, ext, kind, size, path, "source", None, meta)
    f = db.get_file(fid)
    return JSONResponse(_file_payload(f, request))


@app.post("/api/convert")
async def api_convert(request: Request):
    sid = request.state.sid
    body = await request.json()
    fid = str(body.get("id") or "")
    target = str(body.get("target") or "").lower().lstrip(".")
    opts = body.get("opts") or {}
    f = _own(fid, sid)
    if target not in targets_for(f["ext"]):
        raise HTTPException(400, f"из .{f['ext']} нельзя получить .{target}")

    jid = uuid.uuid4().hex[:16]
    db.add_job(jid, sid, fid, target)
    with JOBS_LOCK:
        JOBS[jid] = {"id": jid, "sid": sid, "file_id": fid, "target": target,
                     "opts": opts, "status": "queued", "progress": 0.0,
                     "note": "в очереди", "created": time.time(), "op": "convert"}
    EXEC.submit(_run_convert, jid)
    return {"job": jid}


@app.post("/api/sticker")
async def api_sticker(request: Request):
    sid = request.state.sid
    body = await request.json()
    fid = str(body.get("id") or "")
    mode = body.get("mode") or "static"
    if mode not in ("static", "animated", "video"):
        raise HTTPException(400, "неизвестный режим стикера")
    f = _own(fid, sid)
    if f["kind"] not in ("image", "video"):
        raise HTTPException(400, "стикер делается из изображения или видео")

    jid = uuid.uuid4().hex[:16]
    target = "png" if mode == "static" else "webm"
    db.add_job(jid, sid, fid, f"sticker:{mode}")
    with JOBS_LOCK:
        JOBS[jid] = {"id": jid, "sid": sid, "file_id": fid, "target": target,
                     "opts": {"mode": mode, "mask": bool(body.get("mask")),
                              "fit": body.get("fit") or "contain",
                              "start": float(body.get("start") or 0.0),
                              "duration": float(body.get("duration") or 0.0) or None},
                     "status": "queued", "progress": 0.0, "note": "в очереди",
                     "created": time.time(), "op": "sticker"}
    EXEC.submit(_run_sticker, jid)
    return {"job": jid}


@app.get("/api/job/{jid}")
async def api_job(jid: str, request: Request):
    with JOBS_LOCK:
        job = JOBS.get(jid)
    if not job or job["sid"] != request.state.sid:
        raise HTTPException(404, "задание не найдено")
    out = {"id": jid, "status": job["status"], "progress": round(job["progress"], 1),
           "note": job.get("note"), "error": job.get("error")}
    if job.get("out_id"):
        f = db.get_file(job["out_id"])
        if f:
            out["result"] = _file_payload(f, request)
    return out


@app.get("/api/library")
async def api_library(request: Request):
    sid = request.state.sid
    files = db.list_files(sid)
    return {"files": [_file_payload(f, request) for f in files], "stats": db.stats()}


@app.delete("/api/file/{fid}")
async def api_delete(fid: str, request: Request):
    f = _own(fid, request.state.sid)
    try:
        if os.path.exists(f["path"]):
            os.unlink(f["path"])
    except OSError:
        pass
    db.delete_file(fid)
    return {"ok": True}


@app.get("/api/stats")
async def api_stats():
    return db.stats()


@app.get("/api/text/{fid}")
async def api_text(fid: str, request: Request):
    f = _own(fid, request.state.sid)
    try:
        with open(f["path"], "r", encoding="utf-8", errors="replace") as fh:
            return {"text": fh.read(8000)}
    except Exception:
        raise HTTPException(400, "не текстовый файл")


@app.get("/api/preview/{fid}")
async def api_preview(fid: str, request: Request):
    """Источник для редактора фрагмента: браузерное видео или сгенерированное превью."""
    f = _own(fid, request.state.sid)
    try:
        meta = json.loads(f.get("meta") or "{}")
    except Exception:
        meta = {}
    dur = meta.get("duration")
    ext = f["ext"]

    if f["kind"] == "video" and ext in ("mp4", "webm", "m4v"):
        return {"url": f"/p/{fid}", "duration": dur, "direct": True}

    out = os.path.join(PREVIEW_DIR, f"{fid}.mp4")
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", f["path"],
               "-vf", "scale=480:-2:flags=lanczos,fps=15", "-an",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
        try:
            subprocess.run(cmd, capture_output=True, timeout=240, start_new_session=True)
        except subprocess.TimeoutExpired:
            raise HTTPException(504, "превью не успело собраться")
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        raise HTTPException(400, "не удалось подготовить превью для этого файла")
    if not dur:
        dur = probe(out).get("duration")
    return {"url": f"/preview/{fid}.mp4", "duration": dur, "direct": False}


@app.get("/preview/{fid}.mp4")
async def preview_video(fid: str):
    p = os.path.join(PREVIEW_DIR, f"{fid}.mp4")
    if not os.path.exists(p):
        raise HTTPException(404, "превью не найдено")
    return FileResponse(p, media_type="video/mp4",
                        headers={"Cache-Control": "private, max-age=3600"})


# ------------------------------------------------------------------ файлы

@app.get("/f/{fid}")
async def download(fid: str):
    f = db.get_file(fid)
    if not f or not os.path.exists(f["path"]):
        raise HTTPException(404, "файл не найден")
    return FileResponse(f["path"], media_type=mime_of(f["ext"]), filename=f["name"])


@app.get("/p/{fid}")
async def preview(fid: str):
    f = db.get_file(fid)
    if not f or not os.path.exists(f["path"]):
        raise HTTPException(404, "файл не найден")
    return FileResponse(f["path"], media_type=mime_of(f["ext"]),
                        headers={"Content-Disposition": f'inline; filename="{f["name"]}"',
                                 "Cache-Control": "private, max-age=600"})


@app.get("/poster/{fid}.png")
async def poster(fid: str):
    f = db.get_file(fid)
    if not f:
        raise HTTPException(404, "файл не найден")
    try:
        meta = json.loads(f.get("meta") or "{}")
    except Exception:
        meta = {}
    p = meta.get("poster")
    if not p or not os.path.exists(p):
        raise HTTPException(404, "нет превью")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "private, max-age=600"})


@app.get("/qr/{fid}.png")
async def qr(fid: str, request: Request):
    f = db.get_file(fid)
    if not f:
        raise HTTPException(404, "файл не найден")
    url = f"{base_url(request)}/d/{fid}"
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    # QR зависит от PUBLIC_BASE_URL: кешировать нельзя, иначе после смены
    # адреса браузер продолжает показывать старый код
    return Response(buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/healthz")
async def healthz():
    return {"ok": True, "stats": db.stats()}


# ------------------------------------------------------------------ задания

def _run_convert(jid: str) -> None:
    job = JOBS[jid]
    job["status"] = "running"
    f = db.get_file(job["file_id"])
    out_id = uuid.uuid4().hex[:16]
    out_ext = job["target"]
    out_path = os.path.join(FILES_DIR, job["sid"], f"{out_id}.{out_ext}")

    def cb(p: float, note: str) -> None:
        job["progress"] = max(job["progress"], min(99.0, p * 100))
        job["note"] = note

    try:
        meta = convert(f["path"], f["ext"], out_ext, out_path, job["opts"], cb)
        size = os.path.getsize(out_path)
        name = Path(f["name"]).stem + "." + out_ext
        db.add_file(out_id, job["sid"], name, out_ext, kind_of(out_ext) or f["kind"],
                    size, out_path, "output", f["id"], meta)
        job.update(status="done", progress=100.0, note="готово", out_id=out_id)
        db.finish_job(jid, "done", out_id, None)
    except Exception as e:
        msg = str(e)[:300] or "ошибка конвертации"
        job.update(status="error", error=msg, note="ошибка")
        db.finish_job(jid, "error", None, msg)
        if os.path.exists(out_path):
            try:
                os.unlink(out_path)
            except OSError:
                pass


def _run_sticker(jid: str) -> None:
    job = JOBS[jid]
    job["status"] = "running"
    f = db.get_file(job["file_id"])
    mode = job["opts"]["mode"]
    mask = job["opts"]["mask"]
    out_id = uuid.uuid4().hex[:16]
    out_ext = "png" if mode == "static" else "webm"
    out_path = os.path.join(FILES_DIR, job["sid"], f"{out_id}.{out_ext}")
    poster_path = os.path.join(FILES_DIR, job["sid"], f"{out_id}_poster.png")

    def cb(p: float, note: str) -> None:
        job["progress"] = max(job["progress"], min(99.0, p * 100))
        job["note"] = note

    try:
        if mode == "static":
            meta = stickers.static_sticker(f["path"], f["ext"], out_path, mask,
                                           job["opts"].get("fit", "contain"), cb)
        else:
            meta = stickers.animated_sticker(f["path"], f["ext"], out_path, mask, mode,
                                             job["opts"].get("start", 0.0),
                                             job["opts"].get("duration"), cb)
        stickers.poster(f["path"], f["ext"], poster_path, mask, job["opts"].get("start", 0.0))
        meta["poster"] = poster_path
        meta["mode"] = mode
        size = os.path.getsize(out_path)
        name = Path(f["name"]).stem + ("_sticker." if mode == "static" else "_sticker.webm")
        db.add_file(out_id, job["sid"], name, out_ext, "image" if mode == "static" else "video",
                    size, out_path, "output", f["id"], meta)
        job.update(status="done", progress=100.0, note="готово", out_id=out_id)
        db.finish_job(jid, "done", out_id, None)
    except Exception as e:
        msg = str(e)[:300] or "ошибка сборки стикера"
        job.update(status="error", error=msg, note="ошибка")
        db.finish_job(jid, "error", None, msg)
        for p in (out_path, poster_path):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


# ------------------------------------------------------------------ уборка

def _warmup() -> None:
    """Прогрев LibreOffice: первый запуск создаёт профиль (~30 с)."""
    try:
        import tempfile
        from convert import convert as _conv
        d = tempfile.mkdtemp(prefix="warm_")
        src = os.path.join(d, "warm.txt")
        with open(src, "w") as fh:
            fh.write("warmup\n")
        _conv(src, "txt", "pdf", os.path.join(d, "warm.pdf"), {})
        import shutil as _sh
        _sh.rmtree(d, ignore_errors=True)
    except Exception:
        pass


def _janitor() -> None:
    while True:
        try:
            db.purge_older_than(TTL_DAYS)
            cutoff = time.time() - 3600
            with JOBS_LOCK:
                for jid in [k for k, v in JOBS.items() if v.get("created", 0) < cutoff]:
                    JOBS.pop(jid, None)
        except Exception:
            pass
        time.sleep(6 * 3600)


threading.Thread(target=_janitor, daemon=True).start()
threading.Thread(target=_warmup, daemon=True).start()
