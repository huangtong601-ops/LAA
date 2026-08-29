import sys
from maa.toolkit import Toolkit
from maa.controller import AdbController
from maa.resource import Resource
from maa.tasker import Tasker

Toolkit.init_option(r"E:/LAA/MaaBoilerplate")
adb = r"E:\MuMuPlayer-12.0\shell\adb.exe"
addr = "127.0.0.1:16416"

ctrl = AdbController(adb_path=adb, address=addr)
ctrl.post_connection().wait()
print("connected ->", ctrl.connected)

res = Resource()
res.post_bundle(r"E:/LAA/MaaBoilerplate/assets/resource").wait()
print("resource loaded ->", res.loaded, "nodes ->", res.node_list)

tasker = Tasker()
tasker.bind(res, ctrl)

detail = tasker.post_task("MyTask1").wait().get()
print("task detail ->", detail)
print("RUN_DEV_OK" if detail else "RUN_DEV_FAIL")
