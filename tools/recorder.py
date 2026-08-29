# -*- coding: utf-8 -*-
"""交错战线 - 操作录制器（辅助脚本）

用法（在项目根目录 E:\\LAA\\MaaBoilerplate 下）:
    python tools\\recorder.py start "<操作名>"   # 开始录制（用户告知当前要做的操作）
    python tools\\recorder.py end                # 结束录制并保存
    python tools\\recorder.py status             # 查看进行中的录制
    python tools\\recorder.py list               # 列出已保存的录制

录制内容保存在 record\\<session>\\：
    meta.json       操作名/任务名/开始时间/设备
    recording.json  屏幕序列(截图路径+哈希) 与 点击坐标(原始+显示坐标) 时间线
    step_*.png      每张抓到的界面截图

坐标说明: 游戏为横屏 1920x1080；getevent 给出的原始触摸为纵向面板( X:0-1080, Y:0-1920 )，
本脚本按 90° 旋转映射成显示坐标( disp_x=raw_y, disp_y=1080-raw_x )，并同时保存原始坐标，便于校准。
"""
import json
import os
import re
import subprocess
import sys
import time
import uuid
import hashlib
import struct
import zlib
from pathlib import Path

ADB_DEFAULT = r"E:\MuMuPlayer-12.0\shell\adb.exe"
PROJECT = Path(r"E:\LAA\MaaBoilerplate")
RECORD_DIR = PROJECT / "record"
TOOLSDIR = Path(__file__).resolve().parent
PYTHON = sys.executable or r"E:\LAA\MaaBoilerplate\.venv\Scripts\python.exe"


def adb_path() -> str:
    return os.environ.get("MAA_ADB", ADB_DEFAULT)


def list_devices(adb: str) -> list[str]:
    out = subprocess.run([adb, "devices"], capture_output=True, text=True).stdout
    devs = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device" and parts[0] != "list":
            devs.append(parts[0])
    return devs


def pick_device(adb: str) -> str:
    devs = list_devices(adb)
    for d in devs:
        if d.startswith("emulator-"):
            return d
    return devs[0] if devs else "emulator-5556"


def _new_session(label: str) -> dict:
    sid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    path = RECORD_DIR / sid
    path.mkdir(parents=True, exist_ok=True)
    meta = {
        "session_id": sid,
        "label": label,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "adb": adb_path(),
        "device": None,
    }
    (path / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"sid": sid, "path": path, "meta": meta}


def cmd_start(label: str):
    if not label:
        print("请提供操作名，例如:  start 竞技场出击")
        return 1
    s = _new_session(label)
    print(f"[recorder] 开始录制 session={s['sid']}  label={label}")
    print(f"[recorder] 录制目录: {s['path']}")
    print("[recorder] 请在游戏里执行操作；完成后告诉我，我会执行 end 结束并保存。")
    # 启动后台监视进程
    proc = subprocess.Popen(
        [PYTHON, str(TOOLSDIR / "recorder_monitor.py"), str(s["path"]), adb_path()],
        cwd=str(PROJECT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=0x08000000,  # CREATE_NO_WINDOW
    )
    (s["path"] / "monitor.pid").write_text(str(proc.pid), encoding="utf-8")
    print(f"[recorder] 采集进程已启动 pid={proc.pid}")
    return 0


def cmd_end():
    # 找到最近仍有 monitor.pid 的 session
    if not RECORD_DIR.exists():
        print("没有录制记录。")
        return 1
    sessions = sorted(RECORD_DIR.iterdir(), reverse=True)
    target = None
    for p in sessions:
        if (p / "monitor.pid").exists() or (p / "meta.json").exists():
            if (p / "monitor.pid").exists():
                target = p
                break
            if target is None:
                target = p
    if target is None:
        print("没有找到进行中的录制。")
        return 1
    stop = target / "stop.flag"
    stop.write_text("1", encoding="utf-8")
    pid = None
    try:
        pid = int((target / "monitor.pid").read_text(encoding="utf-8"))
    except Exception:
        pid = None
    # 等待监视进程退出
    for _ in range(60):
        if pid and _pid_alive(pid):
            time.sleep(0.5)
        else:
            break
    rec = target / "recording.json"
    if rec.exists():
        data = json.loads(rec.read_text(encoding="utf-8"))
        print(f"[recorder] 结束录制 session={target.name}")
        print(f"          页面数={len(data.get('screens', []))}  点击数={len(data.get('taps', []))}")
        print(f"          记录文件: {rec}")
        return 0
    else:
        print("[recorder] 监视进程可能未产出记录，请检查。")
        return 1


def _pid_alive(pid: int) -> bool:
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    except Exception:
        return True


def cmd_status():
    print("=== 进行中的录制 ===")
    if RECORD_DIR.exists():
        for p in sorted(RECORD_DIR.iterdir(), reverse=True):
            if (p / "monitor.pid").exists() and not (p / "stop.flag").exists():
                m = json.loads((p / "meta.json").read_text(encoding="utf-8"))
                print(f"{p.name}  label={m['label']}")
    return 0


def cmd_list():
    print("=== 已保存录制 ===")
    if RECORD_DIR.exists():
        for p in sorted(RECORD_DIR.iterdir(), reverse=True):
            if (p / "recording.json").exists():
                m = json.loads((p / "meta.json").read_text(encoding="utf-8"))
                d = json.loads((p / "recording.json").read_text(encoding="utf-8"))
                print(f"{p.name}  label={m['label']}  screens={len(d.get('screens', []))}  taps={len(d.get('taps', []))}")
    return 0


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    cmd = args[0]
    if cmd == "start":
        label = " ".join(args[1:]).strip().strip('"')
        return cmd_start(label)
    if cmd == "end":
        return cmd_end()
    if cmd == "status":
        return cmd_status()
    if cmd == "list":
        return cmd_list()
    print("未知命令:", cmd)
    return 1


if __name__ == "__main__":
    sys.exit(main())
