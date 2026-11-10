"""Регрессия: кириллица в именах файлов не должна ронять превью и скачивание.

Баг был такой: Content-Disposition собирался вручную, а HTTP-заголовки
допускают только latin-1 — на «Снимок экрана.png» сервер отдавал 500.
"""
import http.cookiejar
import json
import os
import sys
import time
import urllib.request
import uuid

BASE = os.environ.get("BASE", "http://192.168.1.194:8080")
D = "/home/hermes/workspace/convert/testdata"

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def upload(path, name):
    boundary = "----forma" + uuid.uuid4().hex
    data = open(path, "rb").read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(BASE + "/api/upload", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(opener.open(req, timeout=120).read())


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(opener.open(req, timeout=60).read())


def get(path):
    return json.loads(opener.open(BASE + path, timeout=60).read())


def wait(job_id, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = get("/api/job/" + job_id)
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.4)
    return {"status": "timeout"}


CASES = [
    ("sample.png", "Снимок экрана_20261021_004740.png", "convert", "jpg"),
    ("sample.png", "фото с пробелами и ёжиком.png", "convert", "webp"),
    ("sample.mp4", "Моё видео 2026.mp4", "sticker", "static"),
]


def main():
    bad = 0
    for src, name, op, arg in CASES:
        up = upload(os.path.join(D, src), name)
        if op == "convert":
            res = wait(post("/api/convert", {"id": up["id"], "target": arg, "opts": {}})["job"])
        else:
            res = wait(post("/api/sticker", {"id": up["id"], "mode": arg, "mask": True})["job"])
        if res["status"] != "done":
            print(f"FAIL {name}: {res.get('error')}")
            bad += 1
            continue
        out = res["result"]
        ok = True
        for path in (f"/p/{out['id']}", f"/f/{out['id']}", f"/d/{out['id']}", f"/qr/{out['id']}.png"):
            try:
                r = urllib.request.urlopen(BASE + path, timeout=30)
                if r.status != 200:
                    ok = False
                    print(f"FAIL {path}: {r.status}")
            except Exception as e:
                ok = False
                print(f"FAIL {path}: {e}")
        # имя на выходе должно сохранять расширение
        if not out["name"].lower().endswith("." + out["ext"]):
            ok = False
            print(f"FAIL имя без расширения: {out['name']}")
        print(("OK   " if ok else "FAIL "), f"{name!r} -> {out['name']!r} ({out['size']} b)")
        bad += 0 if ok else 1
    print(f"\n{'все проверки прошли' if bad == 0 else str(bad) + ' провалов'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
