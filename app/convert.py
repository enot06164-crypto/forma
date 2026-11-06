"""Движок конвертации: изображения, аудио, видео, документы."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from PIL import Image, ImageOps

try:  # HEIC/HEIF
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:  # pragma: no cover
    pass

from formats import kind_of

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
SOFFICE = shutil.which("soffice") or shutil.which("libreoffice") or "soffice"
PDFTOPPM = shutil.which("pdftoppm") or "pdftoppm"
PDFTOTEXT = shutil.which("pdftotext") or "pdftotext"
PDFTOHTML = shutil.which("pdftohtml") or "pdftohtml"
RSVG = shutil.which("rsvg-convert") or "rsvg-convert"


class ConvertError(Exception):
    pass


_LO_LOCK = threading.Lock()


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, start_new_session=True)
    except subprocess.TimeoutExpired:
        raise ConvertError("превышено время обработки")
    if p.returncode != 0:
        err = (p.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        tail = " | ".join(err[-3:]) if err else f"код {p.returncode}"
        raise ConvertError(tail[:400])
    return p


def probe(path: str) -> dict:
    """Метаданные медиафайла через ffprobe."""
    try:
        p = subprocess.run(
            [FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, timeout=60,
        )
        data = json.loads(p.stdout or b"{}")
    except Exception:
        return {}
    fmt = data.get("format", {}) or {}
    streams = data.get("streams", []) or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    meta = {
        "duration": float(fmt.get("duration") or 0) or None,
        "bitrate": int(fmt.get("bit_rate") or 0) or None,
        "format": fmt.get("format_name"),
    }
    if v:
        meta.update({
            "width": v.get("width"), "height": v.get("height"),
            "vcodec": v.get("codec_name"), "fps": _fps(v.get("avg_frame_rate")),
            "has_alpha": _has_alpha(v),
        })
    if a:
        meta.update({"acodec": a.get("codec_name"), "channels": a.get("channels"),
                     "sample_rate": int(a.get("sample_rate") or 0) or None})
    return meta


def _fps(rate: str | None) -> float | None:
    if not rate or "/" not in rate:
        return None
    num, den = rate.split("/")[:2]
    try:
        num, den = float(num), float(den)
        return round(num / den, 2) if den else None
    except ValueError:
        return None


def _has_alpha(stream: dict) -> bool:
    pix = (stream.get("pix_fmt") or "")
    return pix.startswith("yuva") or pix in ("rgba", "bgra", "argb", "abgr", "ya8", "pal8")


def _ffmpeg(args: list[str], duration: float | None, cb, timeout: int = 900) -> None:
    """Запуск ffmpeg с разбором прогресса."""
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-progress", "pipe:1", "-nostats"] + args
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for raw in proc.stdout:  # type: ignore[union-attr]
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("out_time_ms=") and duration:
                try:
                    done = int(line.split("=", 1)[1]) / 1_000_000
                    if cb:
                        cb(min(0.97, max(0.02, done / duration)), "кодирование")
                except ValueError:
                    pass
            elif line == "progress=end" and cb:
                cb(0.99, "финализация")
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise ConvertError("превышено время обработки")
    if proc.returncode != 0:
        err = (proc.stderr.read() or b"").decode("utf-8", "replace").strip().splitlines()
        raise ConvertError((" | ".join(err[-3:]) if err else "ffmpeg error")[:400])


# ---------------------------------------------------------------- изображения

_IMG_FORMAT = {
    "png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP", "gif": "GIF",
    "bmp": "BMP", "tiff": "TIFF", "tif": "TIFF", "ico": "ICO", "avif": "AVIF",
}


def _open_image(src: str, ext: str) -> Image.Image:
    if ext == "svg":
        tmp = tempfile.mktemp(suffix=".png")
        _run([RSVG, "-w", "2048", "-o", tmp, src], timeout=120)
        img = Image.open(tmp)
        img.load()
        os.unlink(tmp)
        return img
    img = Image.open(src)
    img.load()
    return ImageOps.exif_transpose(img)


def convert_image(src: str, ext: str, target: str, dst: str, opts: dict, cb) -> dict:
    if ext == "svg" and target == "pdf":
        _run([RSVG, "-f", "pdf", "-o", dst, src], timeout=120)
        return {"width": None, "height": None}

    img = _open_image(src, ext)
    if cb:
        cb(0.35, "чтение")

    max_dim = int(opts.get("max_dim") or 0)
    if max_dim and max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    quality = int(opts.get("quality") or 88)
    quality = max(40, min(100, quality))

    if target in ("jpg", "jpeg", "bmp", "pdf"):
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")

    if cb:
        cb(0.6, "запись")

    if target == "pdf":
        img.save(dst, "PDF", resolution=150.0)
    elif target == "ico":
        img = img.convert("RGBA")
        img.save(dst, "ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    elif target == "gif":
        img.convert("P", palette=Image.ADAPTIVE, colors=256).save(dst, "GIF", optimize=True)
    elif target == "avif":
        try:
            img.save(dst, "AVIF", quality=quality)
        except Exception:
            tmp = tempfile.mktemp(suffix=".png")
            img.save(tmp, "PNG")
            enc = shutil.which("avifenc")
            if enc:
                _run([enc, "-q", str(max(30, quality)), "-s", "8", "--min", "0", "--max", "63",
                      tmp, dst], timeout=180)
            else:
                _ffmpeg(["-i", tmp, "-c:v", "libaom-av1", "-still-picture", "1",
                         "-crf", str(max(20, 63 - quality // 2)), "-b:v", "0",
                         "-cpu-used", "8", "-row-mt", "1", dst], None, cb)
            os.unlink(tmp)
    elif target in ("jpg", "jpeg"):
        img.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)
    elif target == "webp":
        img.save(dst, "WEBP", quality=quality, method=4)
    elif target == "png":
        img.save(dst, "PNG", optimize=True)
    elif target in ("tiff", "tif"):
        img.save(dst, "TIFF", compression="tiff_deflate")
    elif target == "bmp":
        img.save(dst, "BMP")
    else:
        raise ConvertError(f"неизвестный формат {target}")

    if cb:
        cb(1.0, "готово")
    return {"width": img.size[0], "height": img.size[1]}


# --------------------------------------------------------------------- аудио

_AUDIO_CODEC = {
    "mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
    "wav": ["-c:a", "pcm_s16le"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "5"],
    "opus": ["-c:a", "libopus", "-b:a", "128k"],
    "flac": ["-c:a", "flac", "-compression_level", "5"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
    "aac": ["-c:a", "aac", "-b:a", "192k"],
}


def convert_audio(src: str, target: str, dst: str, opts: dict, cb) -> dict:
    meta = probe(src)
    codec = _AUDIO_CODEC.get(target)
    if not codec:
        raise ConvertError(f"неизвестный аудиоформат {target}")
    args = ["-i", src, "-vn", "-map_metadata", "0"] + codec
    if target in ("m4a", "aac"):
        args += ["-movflags", "+faststart"] if target == "m4a" else ["-f", "adts"]
    args.append(dst)
    _ffmpeg(args, meta.get("duration"), cb)
    return {"duration": meta.get("duration")}


# --------------------------------------------------------------------- видео

def convert_video(src: str, target: str, dst: str, opts: dict, cb) -> dict:
    meta = probe(src)
    dur = meta.get("duration")
    if target in ("mp3", "wav"):
        return convert_audio(src, target, dst, opts, cb)

    if target == "gif":
        fps = int(opts.get("fps") or 12)
        width = int(opts.get("width") or 480)
        vf = (f"fps={fps},scale={width}:-1:flags=lanczos,split[s0][s1];"
              f"[s0]palettegen=max_colors=192[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3")
        _ffmpeg(["-i", src, "-filter_complex", vf, "-loop", "0", dst], dur, cb)
        return {"width": width}

    if target == "mp4":
        args = ["-i", src, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart"]
    elif target == "webm":
        args = ["-i", src, "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0",
                "-row-mt", "1", "-deadline", "good", "-cpu-used", "4",
                "-c:a", "libopus", "-b:a", "96k"]
    elif target == "mkv":
        args = ["-i", src, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "aac", "-b:a", "160k"]
    elif target == "mov":
        args = ["-i", src, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k"]
    else:
        raise ConvertError(f"неизвестный видеоформат {target}")

    args.append(dst)
    _ffmpeg(args, dur, cb)
    return {"duration": dur}


# ----------------------------------------------------------------- документы

def _soffice(src: str, target: str, outdir: str, timeout: int = 420) -> str:
    """Конвертация через LibreOffice.

    Особенность контейнера: первый запуск с новым профилем завершается кодом 81
    и ничего не делает — профиль только инициализируется. Второй запуск с тем же
    профилем работает. Поэтому профиль общий и есть до трёх попыток.
    """
    stem = Path(src).stem
    want = "." + target.split(":")[0].lower()
    with _LO_LOCK:
        for attempt in range(3):
            try:
                _run([SOFFICE, "--headless", "--norestore", "--nolockcheck",
                      "-env:UserInstallation=file:///tmp/lo_profile",
                      "--convert-to", target, "--outdir", outdir, src], timeout=timeout)
            except ConvertError:
                pass
            for f in os.listdir(outdir):
                if f.startswith(stem) and f.lower().endswith(want):
                    return os.path.join(outdir, f)
            time.sleep(0.6)
    raise ConvertError(f"LibreOffice не создал {want}")


def _md_to_html(text: str) -> str:
    """Минимальный markdown → html (заголовки, списки, код, ссылки, выделение)."""
    import html as _html

    lines = text.splitlines()
    out, in_code, in_list = [], False, False
    for line in lines:
        if line.strip().startswith("```"):
            out.append("<pre><code>" if not in_code else "</code></pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(_html.escape(line))
            continue
        s = _html.escape(line)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            if in_list:
                out.append("</ul>")
                in_list = False
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{m.group(2)}</h{lvl}>")
            continue
        if re.match(r"^\s*[-*+]\s+", s):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>" + re.sub(r"^\s*[-*+]\s+", "", s) + "</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        out.append(f"<p>{s}</p>" if s.strip() else "")
    if in_list:
        out.append("</ul>")
    body = "\n".join(out)
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<style>body{font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;"
            "max-width:760px;margin:48px auto;padding:0 20px;color:#111}"
            "pre{background:#f4f4f5;padding:14px;border-radius:8px;overflow:auto}"
            "code{font-family:ui-monospace,Menlo,monospace;font-size:.92em}"
            "h1,h2,h3{line-height:1.25}</style></head><body>" + body + "</body></html>")


def convert_document(src: str, ext: str, target: str, dst: str, opts: dict, cb) -> dict:
    work = tempfile.mkdtemp(prefix="doc_")
    try:
        if cb:
            cb(0.15, "подготовка")

        if ext == "pdf" and target in ("png", "jpg"):
            dpi = int(opts.get("dpi") or 150)
            flag = "-png" if target == "png" else "-jpeg"
            prefix = os.path.join(work, "page")
            _run([PDFTOPPM, "-r", str(dpi), "-f", "1", "-l", "1", flag, src, prefix], timeout=180)
            made = [f for f in os.listdir(work) if f.startswith("page")]
            if not made:
                raise ConvertError("не удалось отрисовать страницу PDF")
            shutil.move(os.path.join(work, made[0]), dst)
            return {"pages": 1, "dpi": dpi}

        if ext == "pdf" and target == "txt":
            _run([PDFTOTEXT, "-layout", "-enc", "UTF-8", src, dst], timeout=180)
            return {}

        if ext == "pdf" and target == "html":
            _run([PDFTOHTML, "-s", "-noframes", "-enc", "UTF-8", src, os.path.join(work, "out.html")], timeout=180)
            made = [f for f in os.listdir(work) if f.endswith(".html")]
            if not made:
                raise ConvertError("не удалось извлечь HTML из PDF")
            shutil.move(os.path.join(work, made[0]), dst)
            return {}

        if ext in ("md", "markdown"):
            text = Path(src).read_text(encoding="utf-8", errors="replace")
            html = _md_to_html(text)
            if target == "html":
                Path(dst).write_text(html, encoding="utf-8")
                return {}
            if target == "txt":
                Path(dst).write_text(re.sub(r"[*_`#>]", "", text), encoding="utf-8")
                return {}
            src = os.path.join(work, "doc.html")
            Path(src).write_text(html, encoding="utf-8")
            ext = "html"

        if cb:
            cb(0.4, "LibreOffice")

        # HTML/Web-документ нельзя экспортировать в docx напрямую — только через odt
        if target == "docx" and ext in ("html", "htm"):
            mid = os.path.join(work, "mid.odt")
            shutil.move(_soffice(src, "odt", work), mid)
            shutil.move(_soffice(mid, "docx", work), dst)
            if cb:
                cb(1.0, "готово")
            return {}

        lo_target = {"jpg": "jpg", "png": "png"}.get(target, target)
        if target == "csv":
            lo_target = "csv"
        produced = _soffice(src, lo_target, work, timeout=420)
        shutil.move(produced, dst)
        if cb:
            cb(1.0, "готово")
        return {}
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ------------------------------------------------------------------ диспетчер

def convert(src: str, ext: str, target: str, dst: str, opts: dict | None = None, cb=None) -> dict:
    opts = opts or {}
    ext = ext.lower().lstrip(".")
    kind = kind_of(ext)
    if not kind:
        raise ConvertError(f"неизвестный тип файла .{ext}")

    if kind == "image":
        # GIF — это и картинка, и источник видео
        if target in ("mp4", "webm", "mkv", "mov"):
            return convert_video(src, target, dst, opts, cb)
        return convert_image(src, ext, target, dst, opts, cb)
    if kind == "audio":
        return convert_audio(src, target, dst, opts, cb)
    if kind == "video":
        return convert_video(src, target, dst, opts, cb)
    if kind == "document":
        return convert_document(src, ext, target, dst, opts, cb)
    raise ConvertError("неподдерживаемый тип")
