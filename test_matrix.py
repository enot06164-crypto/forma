"""Полная проверка матрицы конвертации через HTTP API."""
import http.cookiejar
import json
import os
import sys
import time
import urllib.request
import uuid

BASE = os.environ.get("BASE", "http://192.168.1.194:8080")
D = "/home/hermes/workspace/convert/testdata"
OUT = "/home/hermes/workspace/convert/test_report.jsonl"

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def upload(path):
    boundary = "----forma" + uuid.uuid4().hex
    name = os.path.basename(path)
    with open(path, "rb") as fh:
        data = fh.read()
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


def wait(job_id, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = get("/api/job/" + job_id)
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.35)
    return {"status": "timeout"}


MAGIC = {
    "png": [b"\x89PNG"], "jpg": [b"\xff\xd8\xff"], "webp": [b"RIFF"],
    "avif": [b"ftypavif", b"ftypmif1"], "gif": [b"GIF8"], "bmp": [b"BM"],
    "tiff": [b"II*\x00", b"MM\x00*"], "ico": [b"\x00\x00\x01\x00"],
    "pdf": [b"%PDF"], "mp3": [b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"],
    "wav": [b"RIFF"], "ogg": [b"OggS"], "opus": [b"OggS"], "flac": [b"fLaC"],
    "m4a": [b"ftyp"], "aac": [b"\xff\xf1", b"\xff\xf9", b"ADIF"],
    "mp4": [b"ftyp"], "mov": [b"ftyp", b"moov", b"wide"], "m4v": [b"ftyp"],
    "webm": [b"\x1aE\xdf\xa3"], "mkv": [b"\x1aE\xdf\xa3"],
    "docx": [b"PK\x03\x04"], "xlsx": [b"PK\x03\x04"], "pptx": [b"PK\x03\x04"],
    "odt": [b"PK\x03\x04"], "ods": [b"PK\x03\x04"], "odp": [b"PK\x03\x04"],
    "rtf": [b"{\\rtf"],
}


def check_bytes(ext, data):
    if ext in ("txt", "csv", "html", "htm", "md"):
        try:
            data.decode("utf-8")
            return True, "utf-8 ok"
        except UnicodeDecodeError:
            return False, "не utf-8"
    mags = MAGIC.get(ext)
    if not mags:
        return True, "нет проверки"
    for m in mags:
        if data[:64].find(m) >= 0 or data[:16].startswith(m):
            return True, m.decode("latin-1", "replace")
    return False, "сигнатура не совпала: " + data[:12].hex()


def main():
    files = sorted(f for f in os.listdir(D) if os.path.isfile(os.path.join(D, f)))
    results = []
    with open(OUT, "w") as log:
        for fname in files:
            path = os.path.join(D, fname)
            try:
                up = upload(path)
            except Exception as e:
                print(f"UPLOAD FAIL {fname}: {e}", flush=True)
                continue
            targets = up.get("targets") or []
            print(f"\n=== {fname} ({up['kind']}, {len(targets)} targets)", flush=True)
            for t in targets:
                rec = {"src": fname, "src_ext": up["ext"], "target": t}
                t0 = time.time()
                try:
                    job = post("/api/convert", {"id": up["id"], "target": t, "opts": {}})
                    res = wait(job["job"])
                    rec["status"] = res["status"]
                    rec["secs"] = round(time.time() - t0, 2)
                    if res["status"] == "done":
                        r = res["result"]
                        rec["size"] = r["size"]
                        rec["out_ext"] = r["ext"]
                        data = opener.open(BASE + r["url"], timeout=120).read()
                        ok, why = check_bytes(t, data)
                        rec["magic_ok"] = ok
                        rec["magic"] = why
                        rec["bytes_match"] = len(data) == r["size"]
                        if r.get("meta"):
                            rec["meta"] = {k: r["meta"][k] for k in
                                           ("width", "height", "duration", "vcodec", "acodec", "fps")
                                           if k in r["meta"]}
                    else:
                        rec["error"] = res.get("error")
                except Exception as e:
                    rec["status"] = "exception"
                    rec["error"] = str(e)[:200]
                results.append(rec)
                log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                log.flush()
                mark = "OK " if rec.get("status") == "done" and rec.get("magic_ok") else "FAIL"
                print(f"  {mark} {up['ext']:>5} -> {t:<5} {rec.get('size', 0):>9} b  {rec.get('secs', 0):>6}s  {rec.get('error', '') or rec.get('magic', '')}", flush=True)

    ok = sum(1 for r in results if r.get("status") == "done" and r.get("magic_ok"))
    print(f"\nИТОГО: {ok}/{len(results)} успешных", flush=True)
    with open("/home/hermes/workspace/convert/test_summary.json", "w") as fh:
        json.dump({"total": len(results), "ok": ok, "results": results}, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
