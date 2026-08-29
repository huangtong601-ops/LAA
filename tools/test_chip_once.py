# -*- coding: utf-8 -*-
"""Run the read-only first-view chip scanner from the current game page."""

import sys

ROOT = r"E:\LAA\MaaBoilerplate"
sys.path.insert(0, ROOT + r"\agent")

from maa.controller import AdbController
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit

from chip_filter_flow import ChipFilterFlow


def main():
    Toolkit.init_option(ROOT)
    controller = AdbController(
        adb_path=r"E:\MuMuPlayer-12.0\shell\adb.exe",
        address="127.0.0.1:16416",
        config={
            "extras": {
                "mumu": {"enable": True, "index": 1, "path": "E:/MuMuPlayer-12.0"}
            }
        },
    )
    controller.set_screenshot_use_raw_size(True)
    controller.post_connection().wait()
    print("CONNECTED", controller.connected, flush=True)
    if not controller.connected:
        return 2

    resource = Resource()
    resource.register_custom_action("chip_filter_flow", ChipFilterFlow())
    resource.post_bundle(ROOT + r"\gui\resource").wait()
    print("RESOURCE", resource.loaded, flush=True)
    if not resource.loaded:
        return 3

    tasker = Tasker()
    tasker.bind(resource, controller)
    detail = tasker.post_task("ChipDetailReadTask").wait().get()
    succeeded = bool(detail and detail.status.succeeded)
    print("CHIP_SCAN", "OK" if succeeded else "FAIL", flush=True)
    return 0 if succeeded else 4


if __name__ == "__main__":
    raise SystemExit(main())
