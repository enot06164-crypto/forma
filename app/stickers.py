"""Студия стикеров Telegram: обычные (PNG/WEBP), анимированные и видео (VP9/WebM)."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from convert import ConvertError, _ffmpeg, _run, probe

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

SIZE = 512
STATIC_LIMIT = 512 * 1024          # 512 КБ
ANIM_LIMIT = 64 * 1024             # 64 КБ
VIDEO_LIMIT = 256 * 1024           # 256 КБ
MAX_DURATION = 3.0
FPS = 30

SPECS = {
    "static": {"size": "512×512", "limit": STATIC_LIMIT, "format": "PNG / WEBP", "duration": None},
    "animated": {"size": "512×512", "limit": ANIM_LIMIT, "format": "VP9 / WebM + alpha", "duration": MAX_DURATION},
    "video": {"size": "512×512", "limit": VIDEO_LIMIT, "format": "VP9 / WebM", "duration": MAX_DURATION},
}


def make_mask(size: int = SIZE, supersample: int = 4) -> Image.Image:
    """Круглая маска с сглаженными краями (L-канал)."""
    big = size * supersample
    img = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, big - 1, big - 1), fill=255)
    return img.resize((size, size), Image.LANCZOS)


def _frame(src: str, ext: str, at: float = 0.4) -> Image.Image:
    """Кадр из видео/GIF или само изображение."""
    if ext in ("mp4", "webm", "mkv", "mov", "avi", "m4v", "mpg", "mpeg", "ts", "flv", "wmv", "3gp", "gif"):
        tmp = tempfile.mktemp(suffix=".png")
        _run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(at),
              "-i", src, "-frames:v", "1", tmp], timeout=120)
        if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            _run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", src,
                  "-frames:v", "1", tmp], timeout=120)
        img = Image.open(tmp)
        img.load()
        os.unlink(tmp)
        return img
    img = Image.open(src)
    img.load()
    return ImageOps.exif_transpose(img)


def _fit(img: Image.Image, size: int = SIZE) -> Image.Image:
    """Вписать в квадрат с сохранением пропорций, прозрачный фон."""
    img = img.convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
    return canvas


def static_sticker(src: str, ext: str, dst: str, mask_circle: bool = False,
                   fit: str = "contain", cb=None) -> dict:
    if cb:
        cb(0.2, "кадр")
    img = _frame(src, ext)
    if fit == "cover":
        img = ImageOps.fit(img.convert("RGBA"), (SIZE, SIZE), Image.LANCZOS)
    else:
        img = _fit(img)
    if mask_circle:
        img.putalpha(make_mask())
    if cb:
        cb(0.6, "сборка PNG")

    img.save(dst, "PNG", optimize=True)
    if os.path.getsize(dst) > STATIC_LIMIT:
        q = img.convert("RGBA").quantize(colors=256, method=Image.FASTOCTREE)
        q.save(dst, "PNG", optimize=True)
    if os.path.getsize(dst) > STATIC_LIMIT:
        webp = str(Path(dst).with_suffix(".webp"))
        img.save(webp, "WEBP", quality=92, method=6)
        if os.path.getsize(webp) < os.path.getsize(dst):
            os.replace(webp, dst)
        else:
            os.unlink(webp)
    if cb:
        cb(1.0, "готово")
    return {"width": SIZE, "height": SIZE, "mask": mask_circle}


def _encode_webm(src: str, dst: str, mask_path: str | None, crf: int, fps: int,
                 duration: float, start: float = 0.0, cb=None) -> None:
    vf = (f"[0:v]fps={fps},scale={SIZE}:{SIZE}:force_original_aspect_ratio=decrease,"
          f"format=rgba,pad={SIZE}:{SIZE}:(ow-iw)/2:(oh-ih)/2:color=0x00000000[fg]")
    seek = ["-ss", f"{max(0.0, start):.3f}"] if start and start > 0.01 else []
    if mask_path:
        fc = (vf + f";[1:v]format=gray,scale={SIZE}:{SIZE}[m];[fg][m]alphamerge[v]")
        args = seek + ["-i", src, "-loop", "1", "-i", mask_path, "-filter_complex", fc, "-map", "[v]"]
    else:
        args = seek + ["-i", src, "-filter_complex", vf, "-map", "[fg]"]

    args += ["-t", f"{duration:.2f}", "-an", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
             "-b:v", "0", "-crf", str(crf), "-row-mt", "1", "-deadline", "good",
             "-cpu-used", "4", "-auto-alt-ref", "0", "-lag-in-frames", "0",
             "-metadata:s:v:0", "alpha_mode=1", dst]
    _ffmpeg(args, duration, cb)


def animated_sticker(src: str, ext: str, dst: str, mask_circle: bool = False,
                     mode: str = "animated", start: float = 0.0,
                     duration: float | None = None, cb=None) -> dict:
    limit = ANIM_LIMIT if mode == "animated" else VIDEO_LIMIT
    meta = probe(src)
    src_dur = meta.get("duration") or MAX_DURATION

    start = max(0.0, min(float(start or 0.0), max(0.0, src_dur - 0.2)))
    avail = max(0.2, src_dur - start)
    dur = min(MAX_DURATION, avail, float(duration) if duration else MAX_DURATION)
    dur = max(0.3, dur)

    mask_path = None
    if mask_circle:
        mask_path = tempfile.mktemp(suffix=".png")
        make_mask().save(mask_path)

    ladder = [(30, 30), (36, 30), (42, 30), (48, 30), (54, 30),
              (42, 24), (48, 24), (54, 24), (58, 24),
              (48, 20), (54, 20), (60, 20), (60, 15)]
    best = None
    try:
        for i, (crf, fps) in enumerate(ladder):
            if cb:
                cb(0.1 + 0.8 * i / len(ladder), f"кодирование crf {crf} / {fps} fps")
            _encode_webm(src, dst, mask_path, crf, fps, dur, start, None)
            size = os.path.getsize(dst)
            best = {"crf": crf, "fps": fps, "size": size}
            if size <= limit:
                break
        else:
            # последняя попытка: короче и медленнее
            dur = min(dur, 2.0)
            _encode_webm(src, dst, mask_path, 60, 15, dur, start, None)
            best = {"crf": 60, "fps": 15, "size": os.path.getsize(dst)}
    finally:
        if mask_path and os.path.exists(mask_path):
            os.unlink(mask_path)

    if cb:
        cb(1.0, "готово")
    return {
        "width": SIZE, "height": SIZE, "duration": round(dur, 2),
        "start": round(start, 2), "fps": best["fps"], "crf": best["crf"],
        "mask": mask_circle, "fits": best["size"] <= limit, "limit": limit,
    }


def poster(src: str, ext: str, dst: str, mask_circle: bool = False, at: float = 0.0) -> None:
    """Превью-кадр стикера (PNG с прозрачностью)."""
    img = _fit(_frame(src, ext, at=max(0.0, at)))
    if mask_circle:
        img.putalpha(make_mask())
    img.save(dst, "PNG", optimize=True)
