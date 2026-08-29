# -*- coding: utf-8 -*-
"""洛AA · 操作录制管理器（本地 Web 界面）
运行: python tools\manager.py  然后浏览器打开 http://127.0.0.1:8123
"""
import json
import sys
import time
import uuid
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recorder_monitor import capture_loop, resolve_device

ADB = r"E:\MuMuPlayer-12.0\shell\adb.exe"
PROJECT = Path(r"E:\LAA\MaaBoilerplate")
RECORD = PROJECT / "record"
TOOLS = Path(__file__).resolve().parent
PORT = 8123
CUR = PROJECT / ".cur_session"

STATE = {"session": None, "thread": None, "stop": None, "live": {}}


def now_str():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def new_session(label):
    sid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    d = RECORD / sid
    d.mkdir(parents=True, exist_ok=True)
    meta = {"session_id": sid, "label": label, "created_at": now_str(), "adb": ADB, "device": None}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return sid, d


def set_session(sid):
    """切换到指定会话（不删除任何数据）。"""
    d = RECORD / sid
    if d.exists() and (d / "meta.json").exists():
        m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        STATE["session"] = {"id": m.get("session_id", sid), "dir": str(d),
                            "label": m.get("label", ""), "device": m.get("device")}
        STATE["thread"] = None
        STATE["stop"] = None
        STATE["live"] = {}
        CUR.write_text(sid, encoding="utf-8")
        return True
    return False


def load_cur_session():
    sid = None
    if CUR.exists():
        sid = CUR.read_text(encoding="utf-8").strip()
    if not sid or not (RECORD / sid).exists():
        cands = sorted(RECORD.glob("./*/meta.json"), key=lambda x: x.parent.name, reverse=True)
        if cands:
            sid = cands[0].parent.name
    if sid:
        set_session(sid)


def list_sessions():
    out = []
    if RECORD.exists():
        for d in sorted(RECORD.iterdir(), reverse=True):
            mf = d / "meta.json"
            if mf.exists():
                try:
                    m = json.loads(mf.read_text(encoding="utf-8"))
                    out.append({"id": m.get("session_id", d.name), "label": m.get("label", d.name)})
                except Exception:
                    out.append({"id": d.name, "label": d.name})
    return out


def load_annotations(d: Path) -> dict:
    f = d / "annotations.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_annotations(d: Path, data: dict):
    (d / "annotations.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_operations(recording: dict) -> list:
    operations = recording.get("operations")
    if isinstance(operations, list):
        for index, operation in enumerate(operations, 1):
            operation.setdefault("id", f"op_{index:04d}")
            operation.setdefault("sequence", index)
            operation.setdefault("enabled", True)
        return operations
    operations = []
    for index, tap in enumerate(recording.get("taps", []), 1):
        point = {k: int(tap.get(k, 0)) for k in ("x", "y", "raw_x", "raw_y")}
        operations.append({
            "id": f"legacy_{index:04d}", "sequence": index, "type": "tap",
            "time": tap.get("time", ""), "duration_ms": 0, "distance": 0,
            "start": point, "end": dict(point), "path": [], "enabled": True,
        })
    recording["operations"] = operations
    return operations


def rebuild_legacy_taps(recording: dict):
    taps = []
    for operation in normalize_operations(recording):
        if not operation.get("enabled", True) or operation.get("type") not in ("tap", "long_press"):
            continue
        point = operation.get("end") or operation.get("start") or {}
        taps.append({"time": operation.get("time", ""),
                     "raw_x": int(point.get("raw_x", 0)), "raw_y": int(point.get("raw_y", 0)),
                     "x": int(point.get("x", 0)), "y": int(point.get("y", 0)),
                     "operation_id": operation.get("id")})
    recording["taps"] = taps


def normalize_screens(recording: dict) -> list:
    screens = recording.get("screens")
    if not isinstance(screens, list):
        screens = []
        recording["screens"] = screens
    for screen in screens:
        if isinstance(screen, dict):
            screen.setdefault("enabled", True)
    return screens


class H(BaseHTTPRequestHandler):
    server_version = "Recorder/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception:
            return {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            html = (TOOLS / "manager.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        if path == "/api/status":
            self._json(self.status_payload())
            return
        if path == "/api/screens":
            self._json(self.screens_payload())
            return
        if path == "/api/recordings":
            self._json(self.recordings_payload())
            return
        if path == "/api/operations":
            self._json(self.operations_payload())
            return
        if path == "/api/sessions":
            self._json({"sessions": list_sessions()})
            return
        if path.startswith("/img/"):
            self._serve_img(path)
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()
        if path == "/api/start":
            self._json(self.start_action(body))
            return
        if path == "/api/stop":
            self._json(self.stop_action())
            return
        if path == "/api/annotate":
            self._json(self.annotate_action(body))
            return
        if path == "/api/switch":
            self._json(self.switch_action(body))
            return
        if path == "/api/screens/set-enabled":
            self._json(self.set_screens_enabled_action(body))
            return
        if path == "/api/operations/set-enabled":
            self._json(self.set_operations_enabled_action(body))
            return
        self._json({"error": "not found"}, 404)

    def status_payload(self):
        s = STATE["session"]
        if s:
            d = Path(s["dir"])
            steps = sorted(d.glob("step_*.png"))
            return {"session": {"id": s["id"], "label": s["label"], "device": s.get("device")},
                    "running": bool(STATE["thread"]), "screens": len(steps),
                    "operations": len(STATE.get("live", {}).get("operations", []))}
        return {"session": None, "running": False}

    def screens_payload(self):
        s = STATE["session"]
        if not s:
            return {"session": None, "screens": [], "annotations": {}}
        d = Path(s["dir"])
        an = load_annotations(d)
        steps = sorted(d.glob("step_*.png"))
        states = {}
        rec_file = d / "recording.json"
        if rec_file.exists():
            recording = json.loads(rec_file.read_text(encoding="utf-8"))
            states = {screen.get("image"): screen.get("enabled", True)
                      for screen in normalize_screens(recording) if isinstance(screen, dict)}
        screens, deleted = [], []
        for f in steps:
            item = {"name": f.name, "url": f"/img/{s['id']}/{f.name}"}
            (screens if states.get(f.name, True) else deleted).append(item)
        return {"session": {"id": s["id"], "label": s["label"]},
                "screens": screens, "deleted_screens": deleted, "annotations": an}

    def recordings_payload(self):
        out = []
        if RECORD.exists():
            for d in sorted(RECORD.iterdir(), reverse=True):
                rec = d / "recording.json"
                if rec.exists():
                    r = json.loads(rec.read_text(encoding="utf-8"))
                    operations = normalize_operations(r)
                    screen_defs = normalize_screens(r)
                    meta = None
                    mf = d / "meta.json"
                    if mf.exists():
                        meta = json.loads(mf.read_text(encoding="utf-8"))
                    an = load_annotations(d)
                    out.append({"id": d.name, "label": meta.get("label") if meta else "",
                                "screens": sum(1 for screen in screen_defs if screen.get("enabled", True)),
                                "total_screens": len(screen_defs), "taps": len(r.get("taps", [])),
                                "operations": len(operations),
                                "enabled_operations": sum(1 for op in operations if op.get("enabled", True)),
                                "swipes": sum(1 for op in operations if op.get("type") == "swipe"),
                                "annotated": len(an)})
        return {"recordings": out}

    def operations_payload(self):
        s = STATE["session"]
        if not s:
            return {"session": None, "operations": []}
        if STATE["thread"]:
            operations = list(STATE.get("live", {}).get("operations", []))
        else:
            rec_file = Path(s["dir"]) / "recording.json"
            if not rec_file.exists():
                operations = []
            else:
                recording = json.loads(rec_file.read_text(encoding="utf-8"))
                operations = normalize_operations(recording)
        return {"session": {"id": s["id"], "label": s["label"]},
                "running": bool(STATE["thread"]), "operations": operations}

    def start_action(self, body):
        label = (body.get("label") or "").strip()
        if not label:
            return {"error": "缺少操作名"}
        if STATE["thread"]:
            STATE["stop"].set()
            STATE["thread"].join(timeout=20)
        device = resolve_device(ADB)
        sid, d = new_session(label)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        meta["device"] = device
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        stop = threading.Event()
        live = {}
        thread = threading.Thread(target=capture_loop, args=(d, ADB, device, stop, live), daemon=True)
        thread.start()
        STATE.update({"session": {"id": sid, "dir": str(d), "label": label, "device": device},
                      "thread": thread, "stop": stop, "live": live})
        CUR.write_text(sid, encoding="utf-8")
        return {"ok": True, "session": {"id": sid, "label": label, "device": device}}

    def stop_action(self):
        if STATE["thread"]:
            STATE["stop"].set()
            STATE["thread"].join(timeout=20)
            STATE["thread"] = None
            STATE["stop"] = None
        return {"ok": True}

    def switch_action(self, body):
        sid = body.get("id") or ""
        if set_session(sid):
            return {"ok": True}
        return {"error": "session 不存在"}

    def set_operations_enabled_action(self, body):
        if STATE["thread"]:
            return {"error": "请先停止录制，再整理操作"}
        sid = body.get("session") or ""
        ids = {str(value) for value in body.get("ids", [])}
        enabled = bool(body.get("enabled", True))
        if not sid or Path(sid).name != sid or not ids:
            return {"error": "缺少 session/ids"}
        rec_file = RECORD / sid / "recording.json"
        if not rec_file.exists():
            return {"error": "录制记录不存在"}
        recording = json.loads(rec_file.read_text(encoding="utf-8"))
        operations = normalize_operations(recording)
        changed = 0
        for operation in operations:
            if operation.get("id") in ids:
                operation["enabled"] = enabled
                changed += 1
        rebuild_legacy_taps(recording)
        rec_file.write_text(json.dumps(recording, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "changed": changed, "enabled": enabled}

    def set_screens_enabled_action(self, body):
        if STATE["thread"]:
            return {"error": "请先停止录制，再整理截图"}
        sid = body.get("session") or ""
        names = {str(value) for value in body.get("names", [])}
        enabled = bool(body.get("enabled", True))
        if not sid or Path(sid).name != sid or not names:
            return {"error": "缺少 session/names"}
        if any(not name.startswith("step_") or not name.endswith(".png") or Path(name).name != name for name in names):
            return {"error": "截图名称无效"}
        rec_file = RECORD / sid / "recording.json"
        if not rec_file.exists():
            return {"error": "请先停止录制，再整理截图"}
        recording = json.loads(rec_file.read_text(encoding="utf-8"))
        changed = 0
        for screen in normalize_screens(recording):
            if screen.get("image") in names:
                screen["enabled"] = enabled
                changed += 1
        rec_file.write_text(json.dumps(recording, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "changed": changed, "enabled": enabled}

    def annotate_action(self, body):
        sid = body.get("session")
        file = body.get("file")
        if not sid or not file:
            return {"error": "缺少 session/file"}
        d = RECORD / sid
        if not d.exists():
            return {"error": "session 不存在"}
        an = load_annotations(d)
        an[file] = {"label": (body.get("label") or "").strip(), "regions": body.get("regions", []),
                    "updated": now_str()}
        save_annotations(d, an)
        return {"ok": True}

    def _serve_img(self, path):
        parts = path.split("/")
        if len(parts) < 4:
            self._json({"error": "bad path"}, 404)
            return
        sid, fname = parts[2], unquote(parts[3])
        if not fname.startswith("step_") or not fname.endswith(".png"):
            self._json({"error": "bad file"}, 404)
            return
        f = RECORD / sid / fname
        if not f.exists():
            self._json({"error": "no file"}, 404)
            return
        data = f.read_bytes()
        self._send(200, data, "image/png")


def main():
    load_cur_session()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"[manager] http://127.0.0.1:{PORT}")
    print(f"[manager] 截图目录: {RECORD}")
    server.serve_forever()


if __name__ == "__main__":
    main()
