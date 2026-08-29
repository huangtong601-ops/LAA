# -*- coding: utf-8 -*-
"""竞技场运行器：连接模拟器，注册 arena_loop，运行竞技场任务。
用法(项目根)：
  python tools\arena.py                                  # 真实运行(默认：重复到归零, 尽量刷取高分)
  python tools\arena.py --repeat 自定次数 --count 3 --dry # 干跑(只读+判断+日志)
  python tools\arena.py --repeat 重复挑战直到次数归零
"""
import sys, os
sys.path.insert(0, r"E:\LAA\MaaBoilerplate\agent")
sys.path.insert(0, r"E:\LAA\MaaBoilerplate")

from maa.toolkit import Toolkit
from maa.controller import AdbController
from maa.resource import Resource
from maa.tasker import Tasker
from arena_loop import ArenaLoop

ADB = r"E:\MuMuPlayer-12.0\shell\adb.exe"
ADDR = "127.0.0.1:16416"
EX = {"extras": {"mumu": {"enable": True, "index": 1, "path": "E:/MuMuPlayer-12.0"}}}
PROJ = r"E:\LAA\MaaBoilerplate"


class DryArenaLoop(ArenaLoop):
    def _click_node(self, ctx, node, timeout=3):
        img = ctx.tasker.controller.post_screencap().wait().get()
        rd = ctx.run_recognition(node, img)
        hit = bool(rd and rd.hit)
        print("[dry] 点击节点:", node, "命中=", hit, flush=True)
        return hit

    def _click(self, ctx, x, y):
        print("[dry] 点击坐标:", x, y, flush=True)

    def _back(self, ctx):
        print("[dry] 返回", flush=True)


class ReadPowerArenaLoop(ArenaLoop):
    """实机只读诊断：允许进入部署页和返回，不选择对手、不挑战。"""

    def run(self, context, argv):
        if not self._ensure_arena(context):
            print("[read-power] 未能进入竞技场", flush=True)
            return False
        own = self._read_own_power(context)
        top = self._read_top_row(context, self._shot(context))
        print(
            f"[read-power] 己方={own} 顶部第一位={top['power']} 积分={top['points']}",
            flush=True,
        )
        return own is not None and top["power"] is not None


def main():
    args = list(sys.argv)
    dry = "--dry" in args
    read_power = "--read-power" in args
    for i, a in enumerate(args):
        if a == "--repeat" and i + 1 < len(args):
            os.environ["ARENA_REPEAT"] = args[i + 1]
        if a == "--count" and i + 1 < len(args):
            os.environ["ARENA_COUNT"] = args[i + 1]
    os.environ.setdefault("ARENA_STRATEGY", "尽量刷取高分")
    os.environ.setdefault("ARENA_REPEAT", "重复挑战直到次数归零")
    os.environ.setdefault("ARENA_COUNT", "1")

    Toolkit.init_option(PROJ)
    c = AdbController(adb_path=ADB, address=ADDR, config=EX)
    c.set_screenshot_use_raw_size(True)
    c.post_connection().wait()
    print("connected:", c.connected, flush=True)
    if not c.connected:
        print("设备未连接", flush=True)
        return 1

    r = Resource()
    r.post_bundle(PROJ + "/assets/resource").wait()
    action = ReadPowerArenaLoop() if read_power else (DryArenaLoop() if dry else ArenaLoop())
    r.register_custom_action("arena_loop", action)
    t = Tasker(); t.bind(r, c)
    mode = "只读战力" if read_power else ("干跑" if dry else "真实")
    print(f"运行 竞技场 任务 ... ({mode})", flush=True)
    d = t.post_task("ArenaTask").wait().get()
    print("done:", d, flush=True)
    return 0
if __name__ == "__main__":
    sys.exit(main())

