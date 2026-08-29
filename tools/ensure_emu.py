# -*- coding: utf-8 -*-
"""pretask：连接前确保 MuMu 实例1 运行并打开交错战线。

设计要点：
- 先问 MuMuManager 实例状态；如果模拟器没启动，立刻 launch，不先等旧 ADB 端口。
- ADB 优先使用稳定序列号 emulator-5556；MuMu TCP 端口只作为辅助连接。
- 任何关键步骤失败都返回非 0，让 GUI 停止后续任务。
"""
import json
from pathlib import Path
import subprocess
import sys
import time

ADB = r"E:\MuMuPlayer-12.0\shell\adb.exe"
MU = r"E:\MuMuPlayer-12.0\nx_main\MuMuManager.exe"
VM = 1
EMU_SERIAL = "emulator-5556"
FALLBACK_TCP = "127.0.0.1:16416"
PKG = "com.megagame.crosscore"
ACT = "com.megagame.crosscore/com.mjsdk.app.MJUnityActivity"
INSTANCE_CONFIG = Path(r"E:\LAA\MaaBoilerplate\gui\config\instances\default.json")


def start_game_selected():
    """MFA pretask is global, so only act when the StartGame task is selected."""
    try:
        data = json.loads(INSTANCE_CONFIG.read_text(encoding="utf-8"))
        for item in data.get("TaskItems", []):
            if item.get("entry") == "StartGameTask":
                return bool(item.get("default_check", False))
    except Exception as e:
        print(f"[pretask] 无法读取任务选择状态，跳过自动启动：{e}", flush=True)
    return False


def sh(args, timeout=90):
    try:
        p = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 1, "", str(e)


def mumu_info():
    code, out, err = sh([MU, "info", "--vmindex", str(VM)], timeout=15)
    if code != 0 or not out.strip():
        return {}
    try:
        return json.loads(out)
    except Exception:
        return {}


def mumu_tcp_addr(info=None):
    info = info or mumu_info()
    ip = info.get("adb_host_ip") or "127.0.0.1"
    port = info.get("adb_port")
    return f"{ip}:{port}" if port else FALLBACK_TCP


def is_android_started():
    return bool(mumu_info().get("is_android_started"))


def adb_devices():
    code, out, err = sh([ADB, "devices"], timeout=20)
    devices = {}
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 2 and p[0] != "List":
            devices[p[0]] = p[1]
    return devices


def device_online(serial):
    return adb_devices().get(serial) == "device"


def any_online_device():
    for serial, state in adb_devices().items():
        if state == "device":
            return serial
    return ""


def ensure_mumu_started():
    info = mumu_info()
    if info.get("is_process_started") or info.get("is_android_started"):
        print("[pretask] MuMu 实例已启动，等待 Android 就绪...", flush=True)
    else:
        print("[pretask] MuMu 未启动，正在拉起实例1...", flush=True)
        code, out, err = sh([MU, "control", "--vmindex", str(VM), "launch"], timeout=60)
        if code != 0:
            print(f"[pretask] 拉起 MuMu 失败：{err or out}", flush=True)
            return False

    for _ in range(120):
        if is_android_started():
            print("[pretask] Android 已就绪。", flush=True)
            return True
        time.sleep(1)
    print("[pretask] Android 启动超时。", flush=True)
    return False


def ensure_adb_device():
    sh([ADB, "start-server"], timeout=20)
    tcp = mumu_tcp_addr()
    print(f"[pretask] 检查当前 MuMu 实例 ADB：{tcp}", flush=True)
    for _ in range(40):
        devices = adb_devices()
        if devices.get(tcp) == "device":
            return tcp
        if devices.get(tcp) == "offline":
            sh([ADB, "disconnect", tcp], timeout=20)
        sh([ADB, "connect", tcp], timeout=20)
        time.sleep(0.5)

    return ""


def top_has_pkg(device):
    code, out, err = sh([ADB, "-s", device, "shell", "dumpsys", "activity", "activities"], timeout=30)
    return any(
        ("topResumedActivity" in line or "mResumedActivity" in line) and PKG in line
        for line in out.splitlines()
    )


def launch_game(device):
    if top_has_pkg(device):
        print("[pretask] 交错战线已经位于前台。", flush=True)
        return True

    for _ in range(2):
        sh([ADB, "-s", device, "shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1"], timeout=30)
        for _ in range(20):
            time.sleep(0.5)
            if top_has_pkg(device):
                return True
    sh([ADB, "-s", device, "shell", "am", "start", "-n", ACT], timeout=30)
    time.sleep(4)
    return top_has_pkg(device)


def main():
    if not start_game_selected():
        print("[pretask] 未选择“开始游戏”，不启动 MuMu，也不启动游戏。", flush=True)
        return 0

    if not ensure_mumu_started():
        return 1

    device = ensure_adb_device()
    if not device:
        print("[pretask] ADB 设备连接失败。", flush=True)
        return 1

    print(f"[pretask] adb 设备已在线：{device}", flush=True)
    print("[pretask] 打开 交错战线...", flush=True)
    if not launch_game(device):
        print("[pretask] 打开交错战线失败。", flush=True)
        return 1

    print("[pretask] 完成。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
