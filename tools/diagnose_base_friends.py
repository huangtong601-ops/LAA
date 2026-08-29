# -*- coding: utf-8 -*-
"""Read three friend order libraries without submitting any order."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import subprocess
import sys
import time

from maa.controller import AdbController
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit


ROOT = r"E:\LAA\MaaBoilerplate"
ADB = r"E:\MuMuPlayer-12.0\shell\adb.exe"
ADDRESS = "127.0.0.1:16416"
CAPTURE_DIR = Path(r"E:\LAA\.tmp\base_friend_diagnose")

sys.path.insert(0, rf"{ROOT}\agent")

from base_order_flow import (  # noqa: E402
    BaseOrderFlow,
    FIRST_FRIEND_VISIT,
    NEXT_FRIEND,
    SELECT_FRIEND,
)


KIND_NAMES = {
    "build": "构建票订单",
    "coin": "星币订单",
    "tech": "技术点订单",
}


class DiagnoseThreeFriends(BaseOrderFlow):
    """Navigate with the production flow, but only take screenshots and OCR."""

    def __init__(self):
        super().__init__()

    @staticmethod
    def _capture_device(index):
        remote = f"/sdcard/laa_base_friend_{index}.png"
        local = CAPTURE_DIR / f"friend_{index}.png"
        subprocess.run(
            [ADB, "-s", ADDRESS, "shell", "screencap", "-p", remote],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [ADB, "-s", ADDRESS, "pull", remote, str(local)],
            check=True,
            capture_output=True,
        )
        return local

    def run(self, context, argv):
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        if not self._ensure_own_order(context):
            print("FRIEND_DIAG_ERROR 无法进入自己的订单库", flush=True)
            return False

        self._click(context, SELECT_FRIEND, "选择好友")
        page, _ = self._wait_page(context, "friend_list", timeout=8.0)
        if page is None:
            print("FRIEND_DIAG_ERROR 无法进入好友列表", flush=True)
            return False

        self._click(context, FIRST_FRIEND_VISIT, "第一位好友拜访")
        page, _ = self._wait_page(context, "friend_order", timeout=10.0)
        if page is None:
            print("FRIEND_DIAG_ERROR 无法进入第一位好友订单库", flush=True)
            return False

        results = []
        for friend_index in range(3):
            image = self._shot(context)
            if self._detect_page(context, image) != "friend_order":
                print(
                    f"FRIEND_DIAG_ERROR 第{friend_index + 1}位不是好友订单库",
                    flush=True,
                )
                return False

            title = self._order_title(context, image) or f"第{friend_index + 1}位好友"
            capture_path = self._capture_device(friend_index + 1)
            print(f"FRIEND_CAPTURE {capture_path}", flush=True)
            orders = self._scan_orders(context, image)
            cards = [
                {
                    "slot": order["index"] + 1,
                    "type": KIND_NAMES.get(order["kind"], order["kind"]),
                    "rare": bool(order["rare"]),
                    "cost": order["cost"],
                    "available": bool(order["available"]),
                }
                for order in orders
            ]
            result = {"index": friend_index + 1, "title": title, "orders": cards}
            results.append(result)
            print("FRIEND_RESULT " + json.dumps(result, ensure_ascii=False), flush=True)

            if friend_index == 2:
                break

            previous = title
            self._click(context, NEXT_FRIEND, "下一个好友订单库")
            deadline = time.time() + 8.0
            while time.time() < deadline:
                image = self._shot(context)
                if self._detect_page(context, image) == "friend_order":
                    current = self._order_title(context, image)
                    if current and current != previous:
                        break
                self._sleep(context, 0.4)
            else:
                print(
                    f"FRIEND_DIAG_ERROR 切换第{friend_index + 2}位好友超时",
                    flush=True,
                )
                return False

        print("FRIEND_DIAG_COMPLETE " + json.dumps(results, ensure_ascii=False), flush=True)
        return True


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    Toolkit.init_option(ROOT)
    controller = AdbController(
        adb_path=ADB,
        address=ADDRESS,
        config={
            "extras": {
                "mumu": {
                    "enable": True,
                    "index": 1,
                    "path": "E:/MuMuPlayer-12.0",
                }
            }
        },
    )
    controller.post_connection().wait()
    controller.set_screenshot_use_raw_size(True)
    print("CONNECTED", controller.connected, flush=True)
    if not controller.connected:
        return 2

    resource = Resource()
    resource.register_custom_action("base_friend_diagnose", DiagnoseThreeFriends())
    resource.post_bundle(rf"{ROOT}\gui\resource").wait()
    print("RESOURCE", resource.loaded, flush=True)
    if not resource.loaded:
        return 3

    tasker = Tasker()
    tasker.bind(resource, controller)
    detail = tasker.post_task(
        "BaseExchangeTask",
        {"BaseExchangeTask": {"custom_action": "base_friend_diagnose"}},
    ).wait().get()
    succeeded = bool(detail and detail.status.succeeded)
    print("DIAGNOSE", "OK" if succeeded else "FAIL", flush=True)
    return 0 if succeeded else 4


if __name__ == "__main__":
    raise SystemExit(main())
