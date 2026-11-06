"""Проверка студии стикеров: размеры, кодек, альфа, лимиты Telegram."""
import http.cookiejar
import json
import os
import subprocess
import tempfile
import time
import urllib.request
import uuid

from PIL import Image

BASE = os.environ.get("BASE", "http://192.168.1.194:8080")
D = "/home/hermes/workspace/convert/testdata"
OUT = "/home/hermes/workspace/convert/sticker_report.json"

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def upload(path):
    boundary = "----forma" + uuid.uuid4().hex
    name = os.path.basename(path)
    data = open(path, "rb").read()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(BASE + "/api/upload", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(opener.open(req, timeout=120).read())


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(opener.open(req, timeout=60).read())


def get(path):
    return json.loads(opener.open(BASE + path, timeout=60).read())


def wait(job_id, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = get("/api/job/" + job_id)
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.4)
    return {"status": "timeout"}


def probe(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                       capture_output=True)
    d = json.loads(p.stdout or b"{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    return {
        "codec": v.get("codec_name"), "pix_fmt": v.get("pix_fmt"),
        "width": v.get("width"), "height": v.get("height"),
        "duration": round(float(d.get("format", {}).get("duration") or 0), 2),
        "fps": v.get("avg_frame_rate"),
    }


def alpha_corners(path):
    """Первый кадр → PNG, проверяем альфу в углу и в центре.
    Важно: нативный декодер VP9 в ffmpeg игнорирует альфа-слой, нужен libvpx-vp9."""
    tmp = tempfile.mktemp(suffix=".png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-c:v", "libvpx-vp9",
                    "-i", path, "-frames:v", "1", tmp], check=True)
    im = Image.open(tmp).convert("RGBA")
    w, h = im.size
    corner = im.getpixel((3, 3))[3]
    center = im.getpixel((w // 2, h // 2))[3]
    os.unlink(tmp)
    return corner, center


def run_case(src, mode, mask, limit):
    up = upload(os.path.join(D, src))
    job = post("/api/sticker", {"id": up["id"], "mode": mode, "mask": mask})
    res = wait(job["job"])
    rec = {"src": src, "mode": mode, "mask": mask, "status": res["status"]}
    if res["status"] != "done":
        rec["error"] = res.get("error")
        return rec
    r = res["result"]
    data = opener.open(BASE + r["url"], timeout=120).read()
    tmp = tempfile.mktemp(suffix="." + r["ext"])
    open(tmp, "wb").write(data)
    rec.update({"size": len(data), "ext": r["ext"], "limit": limit, "fits": len(data) <= limit})
    if r["ext"] == "webm":
        rec.update(probe(tmp))
        corner, center = alpha_corners(tmp)
        rec["alpha_corner"] = corner
        rec["alpha_center"] = center
        rec["alpha_ok"] = corner < 40 and center > 200
    else:
        im = Image.open(tmp).convert("RGBA")
        rec["width"], rec["height"] = im.size
        rec["alpha_corner"] = im.getpixel((3, 3))[3]
        rec["alpha_center"] = im.getpixel((256, 256))[3]
        rec["alpha_ok"] = (im.getpixel((3, 3))[3] < 40) if mask else True
    os.unlink(tmp)
    return rec


def main():
    cases = [
        ("sample.png", "static", False, 512 * 1024),
        ("sample.png", "static", True, 512 * 1024),
        ("sample.mp4", "static", True, 512 * 1024),
        ("sample.gif", "static", False, 512 * 1024),
        ("sample.mp4", "animated", False, 64 * 1024),
        ("sample.mp4", "animated", True, 64 * 1024),
        ("sample.gif", "animated", True, 64 * 1024),
        ("sample.mp4", "video", False, 256 * 1024),
        ("sample.mp4", "video", True, 256 * 1024),
    ]
    out = []
    for src, mode, mask, limit in cases:
        rec = run_case(src, mode, mask, limit)
        out.append(rec)
        ok = rec.get("status") == "done" and rec.get("fits") and rec.get("alpha_ok", True)
        print(("OK  " if ok else "FAIL"), src, mode, "mask" if mask else "no-mask",
              rec.get("size"), "b", rec.get("codec", ""), rec.get("pix_fmt", ""),
              f"{rec.get('width')}x{rec.get('height')}", rec.get("duration"),
              "alpha", rec.get("alpha_corner"), "/", rec.get("alpha_center"),
              rec.get("error", ""), flush=True)
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    print("saved", OUT)


if __name__ == "__main__":
    main()
