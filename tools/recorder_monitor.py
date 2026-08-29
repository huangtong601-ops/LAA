# -*- coding: utf-8 -*-
"""采集逻辑：抓屏帧差 + getevent 点击。可作为后台进程(recorder.py)或线程(manager.py)运行。"""
import json
import sys
import time
import zlib
import struct
import hashlib
import math
import subprocess
import threading
from pathlib import Path

import numpy as np

TOUCH_XMAX = 1080.0
TOUCH_YMAX = 1920.0
MOUSE_AXIS_MAX = 65535.0


def resolve_device(adb):
    out = subprocess.run([adb, "devices"], capture_output=True, text=True).stdout
    devs = [l.split()[0] for l in out.splitlines()[1:] if len(l.split()) >= 2 and l.split()[1] == "device" and not l.startswith("List")]
    for d in devs:
        if d.startswith("emulator-"):
            return d
    return devs[0] if devs else "emulator-5556"


def grab_frame(adb, device):
    b = subprocess.run([adb, "-s", device, "exec-out", "screencap"], capture_output=True, timeout=8).stdout
    if len(b) < 16:
        return None
    w, h, fmt, cs = struct.unpack("<IIII", b[:16])
    arr = np.frombuffer(b, dtype=np.uint8, count=w * h * 4, offset=16)
    return arr.reshape(h, w, 4)


def to_png(frame):
    h, w, _ = frame.shape
    raw = frame.tobytes()
    scan = b"".join(b"\x00" + raw[y * w * 4:(y + 1) * w * 4] for y in range(h))

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(scan, 3)) + chunk(b"IEND", b""))


def frame_diff(a, b):
    if a is None or b is None or a.shape != b.shape:
        return 999.0
    fa = a[::4, ::4].astype(np.int16)
    fb = b[::4, ::4].astype(np.int16)
    return float(np.mean(np.abs(fa - fb)))


def display_coord(raw_x, raw_y):
    return int(round(raw_y)), int(round(TOUCH_XMAX - raw_x))


def mouse_display_coord(raw_x, raw_y):
    """Map MuMu's landscape mouse-integration axes to the 1920x1080 frame."""
    return (int(round(raw_x / MOUSE_AXIS_MAX * TOUCH_YMAX)),
            int(round(raw_y / MOUSE_AXIS_MAX * TOUCH_XMAX)))


def button_is_pressed(value):
    value = value.strip().upper()
    if value in ("DOWN", "PRESS", "PRESSED"):
        return True
    if value in ("UP", "RELEASE", "RELEASED"):
        return False
    return int(value, 16) != 0


class GetEventReader(threading.Thread):
    def __init__(self, adb, device, operations, taps, capture_requests, requests_lock, stop):
        super().__init__(daemon=True)
        self.adb, self.device = adb, device
        self.operations, self.taps = operations, taps
        self.capture_requests, self.requests_lock = capture_requests, requests_lock
        self.stop = stop
        self.proc = None
        self.rx = self.ry = None
        self.mx = self.my = None
        self.tid = -1
        self.coord_mode = "touch"
        self.touch_started = None
        self.path = []

    def terminate(self):
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass

    def _sample(self, now):
        if self.touch_started is None:
            return
        if self.coord_mode == "mouse":
            if self.mx is None or self.my is None:
                return
            raw_x, raw_y = self.mx, self.my
            x, y = mouse_display_coord(raw_x, raw_y)
        else:
            if self.rx is None or self.ry is None:
                return
            raw_x, raw_y = self.rx, self.ry
            x, y = display_coord(raw_x, raw_y)
        elapsed = int((now - self.touch_started) * 1000)
        if not self.path or elapsed - self.path[-1]["t_ms"] >= 35:
            self.path.append({"x": x, "y": y, "raw_x": int(raw_x), "raw_y": int(raw_y), "t_ms": elapsed})

    def _begin_touch(self, now, mode):
        if self.touch_started is None:
            self.touch_started = now
            self.path = []
        self.coord_mode = mode
        self._sample(now)

    def _finish_touch(self):
        if self.touch_started is None or not self.path:
            self.touch_started = None
            self.path = []
            return
        now = time.time()
        self._sample(now)
        start, end = self.path[0], self.path[-1]
        duration = max(0, int((now - self.touch_started) * 1000))
        distance = math.hypot(end["x"] - start["x"], end["y"] - start["y"])
        if distance >= 45:
            op_type = "swipe"
        elif duration >= 600:
            op_type = "long_press"
        else:
            op_type = "tap"
        sequence = len(self.operations) + 1
        operation = {
            "id": f"op_{sequence:04d}",
            "sequence": sequence,
            "type": op_type,
            "time": time.strftime("%H:%M:%S") + f".{int(now % 1 * 1000):03d}",
            "duration_ms": duration,
            "distance": round(distance, 1),
            "start": {k: start[k] for k in ("x", "y", "raw_x", "raw_y")},
            "end": {k: end[k] for k in ("x", "y", "raw_x", "raw_y")},
            "path": self.path[::max(1, len(self.path) // 24)],
            "enabled": True,
        }
        self.operations.append(operation)
        if op_type in ("tap", "long_press"):
            self.taps.append({"time": operation["time"], **operation["end"], "operation_id": operation["id"]})
        with self.requests_lock:
            self.capture_requests.extend([
                {"due": now + 0.10, "operation_id": operation["id"], "reason": "operation_immediate"},
                {"due": now + 0.65, "operation_id": operation["id"], "reason": "operation_settled"},
            ])
        self.touch_started = None
        self.path = []

    def run(self):
        try:
            self.proc = subprocess.Popen([self.adb, "-s", self.device, "shell", "getevent", "-lt"],
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1, text=True)
        except Exception:
            return
        for line in self.proc.stdout:
            if self.stop.is_set():
                break
            try:
                if "ABS_MT_POSITION_X" in line:
                    self.rx = int(line.strip().split()[-1], 16)
                elif "ABS_MT_POSITION_Y" in line:
                    self.ry = int(line.strip().split()[-1], 16)
                elif "ABS_X" in line and "ABS_MT_" not in line:
                    self.mx = int(line.strip().split()[-1], 16)
                    if self.touch_started is not None and self.coord_mode == "mouse":
                        self._sample(time.time())
                elif "ABS_Y" in line and "ABS_MT_" not in line:
                    self.my = int(line.strip().split()[-1], 16)
                    if self.touch_started is not None and self.coord_mode == "mouse":
                        self._sample(time.time())
                elif "ABS_MT_TRACKING_ID" in line:
                    v = int(line.strip().split()[-1], 16)
                    if (v & 0xffffffff) == 0xffffffff:
                        self._finish_touch()
                        self.tid = -1
                    else:
                        self.tid = v
                        self.rx = self.ry = None
                        self._begin_touch(time.time(), "touch")
                elif any(button in line for button in ("BTN_TOUCH", "BTN_LEFT", "BTN_MOUSE")):
                    pressed = button_is_pressed(line.strip().split()[-1])
                    mode = "touch" if "BTN_TOUCH" in line else "mouse"
                    if pressed:
                        self._begin_touch(time.time(), mode)
                    else:
                        self._finish_touch()
                elif "SYN_REPORT" in line or "SYN_MT_REPORT" in line:
                    self._sample(time.time())
            except Exception:
                continue
        self._finish_touch()


def capture_loop(session_dir, adb, device, stop, live=None):
    """Capture responsive screenshots and grouped touch operations until stopped."""
    session_dir = Path(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    screens, taps, operations = [], [], []
    capture_requests = []
    requests_lock = threading.Lock()
    if live is not None:
        live.update({"screens": screens, "taps": taps, "operations": operations})
    reader = GetEventReader(adb, device, operations, taps, capture_requests, requests_lock, stop)
    reader.start()

    last_saved = prev = None
    save_idx = 0
    last_save_time = 0.0

    def save_screen(frame, reason="scene_change", operation_id=None):
        nonlocal save_idx, last_saved, last_save_time
        png = to_png(frame)
        p = session_dir / f"step_{save_idx:03d}.png"
        p.write_bytes(png)
        screens.append({"index": save_idx, "image": p.name,
                        "time": time.strftime("%H:%M:%S"),
                        "sha256": hashlib.sha256(png).hexdigest()[:16],
                        "reason": reason, "operation_id": operation_id})
        save_idx += 1
        last_saved = frame.copy()
        last_save_time = time.time()

    while not stop.is_set():
        try:
            frame = grab_frame(adb, device)
        except Exception:
            frame = None
        if frame is None:
            time.sleep(0.3); continue
        if last_saved is None:
            save_screen(frame, "initial"); prev = frame
        else:
            now = time.time()
            with requests_lock:
                due = [r for r in capture_requests if r["due"] <= now]
                capture_requests[:] = [r for r in capture_requests if r["due"] > now]
            d_saved = frame_diff(frame, last_saved)
            d_prev = frame_diff(frame, prev)
            forced = due[-1] if due else None
            if forced and d_saved > 1.2 and now - last_save_time >= 0.16:
                save_screen(frame, forced["reason"], forced["operation_id"])
            elif d_saved > 5.5 and (d_prev < 4.5 or now - last_save_time >= 0.70) and now - last_save_time >= 0.28:
                save_screen(frame)
            prev = frame
        time.sleep(0.18)

    reader.terminate()
    reader.join(timeout=2)
    rec = {"resolution": {"width": 1920, "height": 1080, "touch_xmax": TOUCH_XMAX, "touch_ymax": TOUCH_YMAX},
           "screens": screens, "operations": operations, "taps": taps,
           "capture": {"poll_interval_ms": 180, "operation_snapshots_ms": [100, 650]}}
    (session_dir / "recording.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


def main():
    adb = sys.argv[2]
    session_dir = sys.argv[1]
    device = resolve_device(adb)
    stop = threading.Event()
    print(f"[monitor] device={device} record start", flush=True)
    rec = capture_loop(session_dir, adb, device, stop)
    print(f"[monitor] finished. screens={len(rec['screens'])} taps={len(rec['taps'])}", flush=True)


if __name__ == "__main__":
    main()
