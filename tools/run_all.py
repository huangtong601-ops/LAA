# -*- coding: utf-8 -*-
"""完整实跑：重置到启动页 -> 开始游戏到主界面 -> 竞技场(按策略挑战)。"""
import sys, os, time
sys.path.insert(0, r"E:\LAA\MaaBoilerplate\agent")
sys.path.insert(0, r"E:\LAA\MaaBoilerplate")
import subprocess
from maa.toolkit import Toolkit
from maa.controller import AdbController
from maa.resource import Resource
from maa.tasker import Tasker
from arena_loop import ArenaLoop
from startgame_flow import StartGameFlow

ADB=r"E:\MuMuPlayer-12.0\shell\adb.exe"; ADDR="127.0.0.1:16416"
EX={"extras":{"mumu":{"enable":True,"index":1,"path":"E:/MuMuPlayer-12.0"}}}
PROJ=r"E:\LAA\MaaBoilerplate"; ACT="com.megagame.crosscore/com.mjsdk.app.MJUnityActivity"
os.environ.setdefault("ARENA_REPEAT","自定次数"); os.environ.setdefault("ARENA_COUNT","1"); os.environ.setdefault("ARENA_STRATEGY","尽量完成挑战")

def sh(a,t=90):
    return subprocess.run(a,capture_output=True,text=True,errors="replace",timeout=t).stdout

def main():
    start_only = "--start-only" in sys.argv
    from_current = "--from-current" in sys.argv
    if from_current:
        print("[run_all] 保持当前MuMu页面，由StartGameFlow负责启动游戏...", flush=True)
    else:
        print("[run_all] 重置游戏到启动页...",flush=True)
        sh([ADB,"-s",ADDR,"shell","am","force-stop","com.megagame.crosscore"]); time.sleep(2)
        sh([ADB,"-s",ADDR,"shell","am","start","-n",ACT]); time.sleep(6)
    Toolkit.init_option(PROJ)
    c=AdbController(adb_path=ADB,address=ADDR,config=EX); c.set_screenshot_use_raw_size(True); c.post_connection().wait()
    print("connected",c.connected,flush=True)
    r=Resource(); r.post_bundle(PROJ+"/assets/resource").wait(); print("loaded",r.loaded,flush=True)
    r.register_custom_action("arena_loop",ArenaLoop())
    r.register_custom_action("startgame",StartGameFlow())
    t=Tasker(); t.bind(r,c)
    print("=== 开始游戏 ===",flush=True)
    d1=t.post_task("StartGameTask").wait().get()
    start_ok = bool(d1 and d1.status.succeeded)
    print("StartGameTask ->", "OK" if start_ok else "FAIL", flush=True)
    if not start_ok:
        print("StartGameTask failed; stop task queue before ArenaTask.", flush=True)
        return 1
    if start_only:
        print("[run_all] --start-only：开始游戏验证完成，不进入竞技场。", flush=True)
        return 0
    print("=== 竞技场 ===",flush=True)
    d2=t.post_task("ArenaTask").wait().get()
    print("ArenaTask ->", "OK" if (d2 and d2.status.succeeded) else "FAIL", flush=True)
    print("done",flush=True)
    return 0

if __name__=="__main__":
    sys.exit(main())

