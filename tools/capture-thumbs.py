#!/usr/bin/env python3
"""Capture each student's first-slide / cover into assets/thumbs/{id}.jpg."""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
THUMBS = ROOT / "assets" / "thumbs"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
CDP_PORT = 9334


def slides_id(url: str) -> str:
    m = re.search(r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else ""


def canva_embed(url: str) -> str:
    m = re.search(r"canva\.com/design/([^/?#]+)(?:/([^/?#]+))?", url)
    if not m:
        return ""
    token = m.group(2) if m.group(2) and m.group(2) not in ("view", "edit", "watch") else ""
    return (
        f"https://www.canva.com/design/{m.group(1)}/{token}/view?embed"
        if token
        else f"https://www.canva.com/design/{m.group(1)}/view?embed"
    )


def is_image(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 3000:
        return False
    head = path.read_bytes()[:16]
    return head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff") or head.startswith(b"RIFF")


def curl_to(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["curl", "-fsSL", "--max-time", "30", "-A", UA, "-o", str(dest), url],
        capture_output=True,
    )
    if r.returncode != 0 or not is_image(dest):
        if dest.exists():
            dest.unlink()
        return False
    return True


def ws_connect(ws_url: str) -> socket.socket:
    u = urllib.parse.urlparse(ws_url)
    sock = socket.create_connection((u.hostname, u.port or 80), 15)
    key = base64.b64encode(os.urandom(16)).decode()
    path = u.path + ("?" + u.query if u.query else "")
    sock.sendall(
        (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {u.hostname}:{u.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode()
    )
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("CDP handshake failed")
        buf += chunk
    return sock


def ws_send(sock: socket.socket, payload: str) -> None:
    data = payload.encode()
    header = bytearray([0x81])
    ln = len(data)
    mask = os.urandom(4)
    if ln < 126:
        header.append(0x80 | ln)
    else:
        header.append(0x80 | 126)
        header.extend(struct.pack(">H", ln))
    header.extend(mask)
    sock.sendall(header + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))


def ws_recv(sock: socket.socket):
    def recvn(n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("CDP closed")
            buf += chunk
        return buf

    hdr = recvn(2)
    ln = hdr[1] & 0x7F
    if ln == 126:
        ln = struct.unpack(">H", recvn(2))[0]
    elif ln == 127:
        ln = struct.unpack(">Q", recvn(8))[0]
    data = recvn(ln)
    opcode = hdr[0] & 0x0F
    if opcode == 0x1:
        return json.loads(data.decode())
    return None


class CDP:
    def __init__(self, ws_url: str):
        self.sock = ws_connect(ws_url)
        self.n = 0

    def call(self, method: str, params=None, timeout=60):
        self.n += 1
        msg_id = self.n
        ws_send(self.sock, json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            obj = ws_recv(self.sock)
            if obj and obj.get("id") == msg_id:
                if "error" in obj:
                    raise RuntimeError(obj["error"])
                return obj.get("result", {})
        raise TimeoutError(method)

    def wait_event(self, name: str, timeout=30) -> None:
        end = time.time() + timeout
        while time.time() < end:
            obj = ws_recv(self.sock)
            if obj and obj.get("method") == name:
                return
        raise TimeoutError(name)


def chrome_screenshot(url: str, dest: Path, width=1600, height=900, wait_ms=20000) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--disable-blink-features=AutomationControlled",
            "--force-device-scale-factor=1",
            f"--window-size={width},{height}",
            f"--virtual-time-budget={wait_ms}",
            f"--screenshot={dest}",
            url,
        ],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0 and is_image(dest)


def start_cdp_chrome() -> None:
    subprocess.Popen(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--disable-blink-features=AutomationControlled",
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={ROOT / '.chrome-thumbs'}",
            "--force-device-scale-factor=1",
            "--window-size=1600,900",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(25):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=1) as resp:
                resp.read()
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("Chrome CDP did not start")


def cdp_page() -> CDP:
    with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=5) as resp:
        tabs = json.loads(resp.read().decode())
    tab = next((t for t in tabs if t.get("type") == "page" and t.get("webSocketDebuggerUrl")), None)
    if not tab:
        raise RuntimeError("no CDP page target")
    return CDP(tab["webSocketDebuggerUrl"])


def cdp_screenshot(url: str, dest: Path, wait_s=12) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        cdp = cdp_page()
        cdp.call("Page.enable")
        cdp.call("Network.setUserAgentOverride", {"userAgent": UA})
        cdp.call("Page.navigate", {"url": url})
        try:
            cdp.wait_event("Page.loadEventFired", timeout=25)
        except TimeoutError:
            pass
        time.sleep(wait_s)
        result = cdp.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        dest.write_bytes(base64.b64decode(result["data"]))
        return is_image(dest)
    except Exception as exc:
        print("  cdp error:", exc)
        if dest.exists() and not is_image(dest):
            dest.unlink()
        return False


def crop_letterbox(img: Image.Image, dark=28) -> Image.Image:
    rgb = img.convert("RGB")
    w, h = rgb.size
    px = rgb.load()

    def row_dark(y: int) -> bool:
        sample = [px[x, y] for x in range(0, w, max(1, w // 80))]
        return sum(sum(c < dark for c in p) == 3 for p in sample) >= len(sample) * 0.72

    def col_dark(x: int) -> bool:
        sample = [px[x, y] for y in range(0, h, max(1, h // 80))]
        return sum(sum(c < dark for c in p) == 3 for p in sample) >= len(sample) * 0.72

    top = 0
    while top < h // 3 and row_dark(top):
        top += 1
    bottom = h - 1
    while bottom > h * 2 // 3 and row_dark(bottom):
        bottom -= 1
    left = 0
    while left < w // 4 and col_dark(left):
        left += 1
    right = w - 1
    while right > w * 3 // 4 and col_dark(right):
        right -= 1

    if h - 1 - bottom < 120:
        bottom = min(bottom, int(h * 0.90))

    pad = 2
    box = (
        max(0, left + pad),
        max(0, top + pad),
        min(w, right - pad + 1),
        min(h, bottom - pad + 1),
    )
    if box[2] - box[0] < w * 0.45 or box[3] - box[1] < h * 0.45:
        return rgb
    return rgb.crop(box)


def save_jpg(img: Image.Image, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    rgb = img.convert("RGB")
    rgb.thumbnail((1280, 800), Image.Resampling.LANCZOS)
    rgb.save(dest, "JPEG", quality=86, optimize=True)


def cover_looks_bad(path: Path) -> bool:
    if not is_image(path):
        return True
    im = Image.open(path).convert("RGB")
    st = ImageStat.Stat(im)
    mean = sum(st.mean) / 3
    std = sum(st.stddev) / 3
    if std < 20 and mean > 245:
        return True
    if path.stat().st_size < 14000 and std < 40:
        return True
    return False


def capture_student(student: dict) -> str:
    sid = student["id"]
    url = (student.get("projectUrl") or "").strip()
    dest = THUMBS / f"{sid}.jpg"
    if not url:
        dest.unlink(missing_ok=True)
        return "skip"

    gid = slides_id(url)
    if gid:
        tmp = THUMBS / f"_{sid}-raw.png"
        if curl_to(f"https://docs.google.com/presentation/d/{gid}/export/png", tmp):
            save_jpg(Image.open(tmp), dest)
            tmp.unlink(missing_ok=True)
            return "slides-export"
        preview = f"https://docs.google.com/presentation/d/{gid}/preview"
        if cdp_screenshot(preview, tmp, wait_s=8):
            save_jpg(crop_letterbox(Image.open(tmp)), dest)
            tmp.unlink(missing_ok=True)
            if cover_looks_bad(dest):
                dest.unlink(missing_ok=True)
                return "fail-slides-private"
            return "slides-screenshot"
        tmp.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)
        return "fail-slides"

    embed = canva_embed(url)
    if embed:
        tmp = THUMBS / f"_{sid}-raw.png"
        if chrome_screenshot(embed, tmp, wait_ms=22000):
            save_jpg(crop_letterbox(Image.open(tmp)), dest)
            tmp.unlink(missing_ok=True)
            time.sleep(2)
            if cover_looks_bad(dest):
                dest.unlink(missing_ok=True)
                return "fail-canva"
            return "canva-screenshot"
        tmp.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)
        return "fail-canva"

    return "unknown"


def recrop_existing_canva(data: dict) -> None:
    for cls in ("A", "B", "C"):
        for student in data.get(cls, []):
            url = student.get("projectUrl") or ""
            dest = THUMBS / f"{student['id']}.jpg"
            if "canva.com" not in url or not dest.exists() or cover_looks_bad(dest):
                continue
            save_jpg(crop_letterbox(Image.open(dest)), dest)


def main() -> int:
    only = set(sys.argv[1:])
    data = json.loads((ROOT / "data" / "students.json").read_text())
    THUMBS.mkdir(parents=True, exist_ok=True)
    recrop_existing_canva(data)

    need = []
    for cls in ("A", "B", "C"):
        for student in data.get(cls, []):
            if only and student["id"] not in only:
                continue
            dest = THUMBS / f"{student['id']}.jpg"
            url = (student.get("projectUrl") or "").strip()
            if not url:
                continue
            if dest.exists() and not cover_looks_bad(dest) and not only:
                continue
            need.append(student)

    if any(slides_id(s.get("projectUrl") or "") for s in need):
        start_cdp_chrome()

    ok = fail = skip = kept = 0
    try:
        for cls in ("A", "B", "C"):
            for student in data.get(cls, []):
                dest = THUMBS / f"{student['id']}.jpg"
                url = (student.get("projectUrl") or "").strip()
                if only and student["id"] not in only:
                    if dest.exists() and not cover_looks_bad(dest):
                        student["thumbUrl"] = f"assets/thumbs/{student['id']}.jpg"
                    else:
                        student.pop("thumbUrl", None)
                    continue
                if not url:
                    print(f"{student['id']}\t{student['name']}\tskip")
                    student.pop("thumbUrl", None)
                    dest.unlink(missing_ok=True)
                    skip += 1
                    continue
                if dest.exists() and not cover_looks_bad(dest) and not only:
                    student["thumbUrl"] = f"assets/thumbs/{student['id']}.jpg"
                    print(f"{student['id']}\t{student['name']}\tkeep")
                    kept += 1
                    continue
                status = capture_student(student)
                print(f"{student['id']}\t{student['name']}\t{status}")
                if status.startswith("fail") or status == "unknown":
                    fail += 1
                    student.pop("thumbUrl", None)
                elif status == "skip":
                    skip += 1
                    student.pop("thumbUrl", None)
                else:
                    ok += 1
                    student["thumbUrl"] = f"assets/thumbs/{student['id']}.jpg"
    finally:
        subprocess.run(["pkill", "-f", str(ROOT / ".chrome-thumbs")], capture_output=True)

    (ROOT / "data" / "students.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"done ok={ok} keep={kept} skip={skip} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
