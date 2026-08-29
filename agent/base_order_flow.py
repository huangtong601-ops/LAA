# -*- coding: utf-8 -*-
"""Base order-library automation built from recording 20260828-175606-4cc346."""

from __future__ import annotations

from collections import Counter
from datetime import date
import json
import logging
from pathlib import Path
import re
import time

from maa.custom_action import CustomAction

from navigation import HOME_BUTTON, is_idle_main_ui, is_main_ui, main_control_point
from stop_guard import ActionStopped, cancelled, ensure_running


log = logging.getLogger("laa.base_order")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTANCE_CONFIG = PROJECT_ROOT / "gui" / "config" / "instances" / "default.json"
DAILY_STATE = PROJECT_ROOT / "config" / "base_order_daily.json"

BASE_ENTRY = main_control_point("base")
BASE_EXCHANGE = (1700, 499)
SELECT_FRIEND = (200, 950)
FIRST_FRIEND_VISIT = (467, 783)
NEXT_FRIEND = (318, 950)
BACK_BUTTON = (164, 68)
REWARD_BLANK = (1210, 900)
CONFIRM_ORDER = (1139, 677)

INVENTORY_POINTS = {
    "coin": (150, 290),
    "tech": (150, 440),
    "build": (150, 590),
}
INVENTORY_ROIS = {
    "coin": [180, 252, 90, 78],
    "tech": [180, 398, 90, 78],
    "build": [180, 542, 90, 82],
}
SYNTHESIS_PRODUCTS = {
    "coin": (750, 610),
    "tech": (1490, 610),
    "build": (510, 890),
}
SYNTHESIS_MIN = (1405, 540)
SYNTHESIS_PLUS = (1660, 540)
SYNTHESIS_CONFIRM = (1595, 940)

CARD_X = (440, 780, 1120, 1460)
CARD_Y = (150, 610)
CARDS = tuple(
    {
        "index": row * 4 + col,
        "x": x,
        "y": y,
        "roi": [x, y, 295, 410],
        "cost_roi": [x + 5, y + 260, 245, 100],
        "tag_roi": [x, y, 135, 62],
        "button_roi": [x, y + 352, 295, 60],
        "button": (x + 148, y + 382),
    }
    for row, y in enumerate(CARD_Y)
    for col, x in enumerate(CARD_X)
)


class BaseOrderFlow(CustomAction):
    """Process own orders, visit each friend, and synthesize exact shortages."""

    def __init__(self):
        super().__init__()
        self.settings = None
        self.friend_completed = set()

    @staticmethod
    def _normalize(text):
        return re.sub(r"\s+", "", str(text or "")).replace("：", ":")

    @staticmethod
    def _checkbox_cases(item, case_names, defaults):
        if not isinstance(item, dict):
            return set(defaults)
        selected = item.get("selected_cases")
        if isinstance(selected, list):
            return {str(value) for value in selected}
        indices = item.get("index")
        if isinstance(indices, list):
            return {
                case_names[index]
                for index in indices
                if isinstance(index, int) and 0 <= index < len(case_names)
            }
        return set(defaults)

    @classmethod
    def _checkbox_enabled(cls, item, case_name, default=False):
        defaults = {case_name} if default else set()
        return case_name in cls._checkbox_cases(item, [case_name], defaults)

    def _read_settings(self):
        settings = {
            "build_costs": {6, 8, 16},
            "build_synth": False,
            "rare_coin": False,
            "rare_coin_synth": False,
            "rare_tech": False,
            "rare_tech_synth": False,
        }
        try:
            data = json.loads(INSTANCE_CONFIG.read_text(encoding="utf-8"))
            task = next(
                item for item in data.get("TaskItems", [])
                if item.get("entry") == "BaseExchangeTask"
            )
            options = {item.get("name"): item for item in task.get("option", [])}

            build = self._checkbox_cases(
                options.get("构建票订单数额6-10"), ["6", "8", "10"], {"6", "8"}
            ) | self._checkbox_cases(
                options.get("构建票订单数额16-18"), ["16", "18"], {"16"}
            )
            settings["build_costs"] = {
                int(value) for value in build if value.isdigit()
            }
            settings["build_synth"] = self._checkbox_enabled(
                options.get("默认兑换构建票订单数额"),
                "缺少素材时自动合成",
            )

            coin = options.get("兑换稀有星币订单")
            settings["rare_coin"] = self._checkbox_enabled(
                coin, "兑换稀有星币订单"
            )
            coin_sub = {
                item.get("name"): item for item in (coin or {}).get("sub_options", [])
            }
            settings["rare_coin_synth"] = settings["rare_coin"] and self._checkbox_enabled(
                coin_sub.get("稀有星币订单缺少素材时自动合成"),
                "缺少素材时自动合成",
            )

            tech = options.get("兑换稀有技术点订单")
            settings["rare_tech"] = self._checkbox_enabled(
                tech, "兑换稀有技术点订单"
            )
            tech_sub = {
                item.get("name"): item for item in (tech or {}).get("sub_options", [])
            }
            settings["rare_tech_synth"] = settings["rare_tech"] and self._checkbox_enabled(
                tech_sub.get("稀有技术点订单缺少素材时自动合成"),
                "缺少素材时自动合成",
            )
        except Exception as exc:
            log.warning("读取基建-订单库设置失败，使用安全默认值：%s", exc)
        return settings

    def _load_daily_state(self):
        today = date.today().isoformat()
        try:
            data = json.loads(DAILY_STATE.read_text(encoding="utf-8"))
            if data.get("date") == today:
                self.friend_completed = set(map(str, data.get("friend_completed", [])))
                return
        except Exception:
            pass
        self.friend_completed = set()

    def _save_daily_state(self):
        DAILY_STATE.parent.mkdir(parents=True, exist_ok=True)
        DAILY_STATE.write_text(
            json.dumps(
                {
                    "date": date.today().isoformat(),
                    "friend_completed": sorted(self.friend_completed),
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _sleep(context, seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            ensure_running(context)
            time.sleep(min(0.1, max(0.0, deadline - time.time())))

    @staticmethod
    def _shot(context):
        ensure_running(context)
        return context.tasker.controller.post_screencap().wait().get()

    @staticmethod
    def _click(context, point, label):
        ensure_running(context)
        context.tasker.controller.post_click(*point).wait()
        log.info("按录制点击%s坐标(%d,%d)", label, point[0], point[1])

    def _ocr(self, context, image, roi, node="BaseScreenText"):
        ensure_running(context)
        try:
            detail = context.run_recognition(
                node,
                image,
                pipeline_override={node: {"roi": roi, "text": [], "threshold": 0.2}},
            )
            if not detail or not detail.hit:
                return ""
            return " ".join(
                str(getattr(item, "text", "")) for item in (detail.all_results or [])
            )
        except Exception as exc:
            log.warning("订单库OCR失败(%s, %s)：%s", node, roi, exc)
            return ""

    @staticmethod
    def _color_ratio(image, roi, kind):
        try:
            x, y, w, h = roi
            crop = image[y:y + h:3, x:x + w:3]
            if crop.size == 0:
                return 0.0
            c0 = crop[:, :, 0].astype("int16")
            c1 = crop[:, :, 1].astype("int16")
            c2 = crop[:, :, 2].astype("int16")
            if kind == "red":
                mask = ((c2 > 165) & (c2 > c1 * 1.25) & (c2 > c0 * 1.25)) | (
                    (c0 > 165) & (c0 > c1 * 1.25) & (c0 > c2 * 1.25)
                )
            elif kind == "yellow":
                mask = ((c2 > 175) & (c1 > 135) & (c0 < 125)) | (
                    (c0 > 175) & (c1 > 135) & (c2 < 125)
                )
            else:
                return 0.0
            return float(mask.mean())
        except Exception:
            return 0.0

    def _screen_text(self, context, image):
        return self._normalize(self._ocr(context, image, [0, 0, 1920, 1080]))

    def _order_title(self, context, image):
        return self._normalize(
            self._ocr(context, image, [520, 30, 1040, 100], "BaseOrderTitle")
        )

    def _detect_page(self, context, image):
        if is_main_ui(context, image):
            return "main"
        if is_idle_main_ui(context, image):
            return "main_idle"

        text = self._screen_text(context, image)
        if "合成份数" in text and "确定" in text:
            return "synthesis_detail"
        if sum(name in text for name in ("星币原料", "数据硬盘", "稀有黑匣")) >= 2:
            return "synthesis_catalog"
        if "好友列表" in text or ("好友数量" in text and "拜访" in text):
            return "friend_list"
        if "订单库" in text and ("交付" in text or "告罄" in text or "制作素材" in text):
            if "好友交付次数共享" in text:
                return "friend_order"
            if "选择合适驻员" in text:
                return "own_order"
            title = self._order_title(context, image)
            if re.search(r"[^:：]{1,20}的\d+级订单库", title):
                return "friend_order"
            return "own_order"
        buildings = ("行星指挥部", "能源发电站", "合成工厂", "研发中心", "原料交易所", "挖掘矿场")
        if "基地建造" in text or sum(name in text for name in buildings) >= 2:
            return "base"
        if "获得物品" in text:
            return "reward"
        return "unknown"

    def _wait_page(self, context, wanted, timeout=8.0):
        wanted = {wanted} if isinstance(wanted, str) else set(wanted)
        deadline = time.time() + timeout
        while time.time() < deadline:
            image = self._shot(context)
            page = self._detect_page(context, image)
            if page in wanted:
                return page, image
            if page == "reward":
                self._click(context, REWARD_BLANK, "获得物品空白处")
            self._sleep(context, 0.45)
        return None, self._shot(context)

    @staticmethod
    def _main_base_point(context, image):
        """Use the recognized label so both home-screen skins click correctly."""
        try:
            detail = context.run_recognition("NavMainBaseText", image)
            if detail and detail.hit and detail.box:
                return (
                    detail.box.x + detail.box.w // 2,
                    detail.box.y + detail.box.h // 2,
                )
        except Exception:
            pass
        return BASE_ENTRY

    def _ensure_own_order(self, context):
        for attempt in range(10):
            image = self._shot(context)
            page = self._detect_page(context, image)
            log.info("订单库导航第%d轮：当前页面=%s", attempt + 1, page)
            if page == "own_order":
                return True
            if page == "main_idle":
                self._click(context, (960, 540), "唤醒主界面")
            elif page == "main":
                self._click(context, self._main_base_point(context, image), "主界面基地")
            elif page == "base":
                self._click(context, BASE_EXCHANGE, "原料交易所换票区")
            elif page in ("synthesis_detail", "synthesis_catalog", "friend_list"):
                self._click(context, BACK_BUTTON, "返回上一级")
            elif page == "reward":
                self._click(context, REWARD_BLANK, "奖励空白处")
            else:
                # Other task pages are more than two transitions away from the order library.
                self._click(context, HOME_BUTTON, "跨任务返回主界面")
            self._sleep(context, 1.4)
        log.error("无法导航到自主订单库")
        return False

    @staticmethod
    def _kind_from_text(text):
        if "构建订" in text:
            return "build"
        if "星币订" in text:
            return "coin"
        if "技术点订" in text or "技术订" in text:
            return "tech"
        return None

    @staticmethod
    def _parse_cost(text):
        values = [int(value) for value in re.findall(r"\d+", text)]
        values = [value for value in values if 0 < value <= 99]
        return values[-1] if values else None

    @staticmethod
    def _order_signature(order):
        # The game's friend-wide daily limit treats, for example, every
        # normal build order costing 18 as the same order. Reward text does
        # not create a separate daily allowance.
        return "%s:%s:%s" % (
            order["kind"],
            "rare" if order["rare"] else "normal",
            order["cost"],
        )

    def _scan_orders(self, context, image):
        orders = []
        for card in CARDS:
            text = self._normalize(self._ocr(context, image, card["roi"], "BaseOrderCard"))
            if not text or "告罄" in text:
                continue
            kind = self._kind_from_text(text)
            if kind is None:
                continue
            cost_text = self._normalize(
                self._ocr(context, image, card["cost_roi"], "BaseOrderCost")
            )
            cost = self._parse_cost(cost_text)
            if cost is None:
                log.warning("订单卡%d识别到%s但未识别出消耗数量：%s", card["index"] + 1, kind, cost_text)
                continue
            rare = "稀有" in text or self._color_ratio(image, card["tag_roi"], "red") > 0.055
            available = "可交付" in text or self._color_ratio(image, card["button_roi"], "yellow") > 0.16
            short_material = "资源暂缺" in text or "素材不足" in text
            order = {
                **card,
                "kind": kind,
                "cost": cost,
                "rare": rare,
                "available": available,
                "short_material": short_material,
                "text": text,
            }
            order["signature"] = self._order_signature(order)
            orders.append(order)
            log.info(
                "订单卡%d：类型=%s 稀有=%s 消耗=%s 可交付=%s",
                card["index"] + 1, kind, rare, cost, available,
            )
        return orders

    def _eligible(self, order, friend):
        kind = order["kind"]
        if kind == "build":
            enabled = order["cost"] in self.settings["build_costs"]
        elif kind == "coin":
            enabled = order["rare"] and self.settings["rare_coin"]
        elif kind == "tech":
            enabled = order["rare"] and self.settings["rare_tech"]
        else:
            enabled = False
        if not enabled:
            return False
        return not (friend and order["signature"] in self.friend_completed)

    def _auto_synth_enabled(self, kind):
        return bool(self.settings.get({
            "build": "build_synth",
            "coin": "rare_coin_synth",
            "tech": "rare_tech_synth",
        }[kind]))

    def _read_number(self, context, image, roi, node="BaseOrderInventory", maximum=999999):
        text = self._normalize(self._ocr(context, image, roi, node))
        values = [int(value) for value in re.findall(r"\d+", text)]
        values = [value for value in values if 0 <= value <= maximum]
        return values[-1] if values else None

    def _stable_inventory(self, context, kind):
        readings = []
        for _ in range(5):
            value = self._read_number(context, self._shot(context), INVENTORY_ROIS[kind])
            if value is not None:
                readings.append(value)
                if Counter(readings)[value] >= 2:
                    log.info("%s订单素材库存=%d（读数=%s）", kind, value, readings)
                    return value
            self._sleep(context, 0.2)
        log.warning("无法稳定读取%s订单素材库存：%s", kind, readings)
        return None

    def _return_to_order(self, context):
        for _ in range(5):
            image = self._shot(context)
            page = self._detect_page(context, image)
            if page in ("own_order", "friend_order"):
                return page
            if page == "reward":
                self._click(context, REWARD_BLANK, "合成奖励空白处")
            elif page in ("synthesis_detail", "synthesis_catalog"):
                self._click(context, BACK_BUTTON, "合成流程返回")
            else:
                return None
            self._sleep(context, 1.0)
        return None

    def _synthesize_missing(self, context, kind, missing):
        if missing <= 0:
            return True
        log.info("%s订单素材缺少%d，进入制作素材", kind, missing)
        self._click(context, INVENTORY_POINTS[kind], "%s订单素材入口" % kind)
        page, _ = self._wait_page(context, "synthesis_catalog", timeout=8.0)
        if page is None:
            log.warning("未进入制作素材页面")
            return False

        self._click(context, SYNTHESIS_PRODUCTS[kind], "%s素材卡" % kind)
        page, _ = self._wait_page(context, "synthesis_detail", timeout=8.0)
        if page is None:
            log.warning("未进入%s素材合成详情", kind)
            self._return_to_order(context)
            return False

        self._click(context, SYNTHESIS_MIN, "合成份数最少")
        self._sleep(context, 0.35)
        for _ in range(max(0, missing - 1)):
            self._click(context, SYNTHESIS_PLUS, "合成份数加一")
            self._sleep(context, 0.12)

        readings = []
        for _ in range(4):
            value = self._read_number(
                context, self._shot(context), [1370, 270, 455, 180],
                "BaseSynthesisCount", maximum=999,
            )
            if value is not None:
                readings.append(value)
                if Counter(readings)[value] >= 2:
                    break
            self._sleep(context, 0.2)
        actual = Counter(readings).most_common(1)[0][0] if readings else None
        if actual != missing:
            log.warning("合成份数未确认或不等于缺口：目标=%d 读数=%s", missing, readings)
            self._return_to_order(context)
            return False

        self._click(context, SYNTHESIS_CONFIRM, "合成确定")
        self._sleep(context, 1.2)
        returned = self._return_to_order(context)
        if returned is None:
            log.warning("合成后未返回订单库")
            return False
        log.info("已合成%s订单素材%d个并返回%s", kind, missing, returned)
        return True

    def _submit_order(self, context, order, friend):
        self._click(context, order["button"], "订单卡%d交付" % (order["index"] + 1))
        deadline = time.time() + 5.0
        confirmed = False
        while time.time() < deadline:
            image = self._shot(context)
            text = self._screen_text(context, image)
            if "确认提交订单" in text or ("提交订单" in text and "确定" in text):
                self._click(context, CONFIRM_ORDER, "提交订单确定")
                confirmed = True
                break
            if self._detect_page(context, image) not in ("own_order", "friend_order"):
                self._sleep(context, 0.35)
            else:
                self._sleep(context, 0.2)
        if not confirmed:
            log.warning("点击交付后未识别到提交确认弹窗")
            return False

        page, _ = self._wait_page(context, ("own_order", "friend_order"), timeout=8.0)
        if page is None:
            log.warning("订单提交后未回到订单库")
            return False
        if friend:
            self.friend_completed.add(order["signature"])
            self._save_daily_state()
        log.info("订单交付完成：%s", order["signature"])
        return True

    def _process_library(self, context, friend):
        blocked = set()
        completed = 0
        for _ in range(32):
            ensure_running(context)
            image = self._shot(context)
            page = self._detect_page(context, image)
            if page not in ("own_order", "friend_order"):
                log.warning("处理订单时页面离开订单库：%s", page)
                return False, completed

            orders = self._scan_orders(context, image)
            candidates = [
                order for order in orders
                if self._eligible(order, friend) and order["signature"] not in blocked
            ]
            if not candidates:
                return True, completed

            acted = False
            for order in candidates:
                if order["available"]:
                    if self._submit_order(context, order, friend):
                        completed += 1
                        blocked.clear()
                        acted = True
                        break
                    blocked.add(order["signature"])
                    continue

                if not order["short_material"]:
                    log.info("订单当前不可交付且并非素材不足，跳过：%s", order["signature"])
                    blocked.add(order["signature"])
                    continue
                if not self._auto_synth_enabled(order["kind"]):
                    blocked.add(order["signature"])
                    continue
                inventory = self._stable_inventory(context, order["kind"])
                if inventory is None:
                    blocked.add(order["signature"])
                    continue
                missing = order["cost"] - inventory
                if missing <= 0:
                    log.warning("库存看似足够但订单不可交付，跳过：%s", order["signature"])
                    blocked.add(order["signature"])
                    continue
                if self._synthesize_missing(context, order["kind"], missing):
                    blocked.clear()
                    acted = True
                    break
                blocked.add(order["signature"])

            if not acted:
                return True, completed
            self._sleep(context, 0.8)
        log.warning("单个订单库达到安全循环上限")
        return False, completed

    def _visit_friends(self, context):
        self._click(context, SELECT_FRIEND, "选择好友")
        page, _ = self._wait_page(context, "friend_list", timeout=8.0)
        if page is None:
            log.warning("未进入好友列表")
            return False, 0
        self._click(context, FIRST_FRIEND_VISIT, "第一位好友拜访")
        page, image = self._wait_page(context, ("friend_order", "own_order"), timeout=10.0)
        if page is None:
            log.warning("拜访后未进入订单库")
            return False, 0

        total = 0
        seen_titles = set()
        for index in range(60):
            ensure_running(context)
            image = self._shot(context)
            page = self._detect_page(context, image)
            if page == "own_order":
                log.info("好友订单库遍历完成，已回到自主订单库")
                return True, total
            if page != "friend_order":
                log.warning("好友遍历时页面异常：%s", page)
                return False, total

            title = self._order_title(context, image)
            if title and title in seen_titles:
                log.warning("好友订单库标题重复，停止循环以避免无限切换：%s", title)
                return False, total
            if title:
                seen_titles.add(title)
            log.info("检查第%d个好友订单库：%s", index + 1, title or "标题未识别")
            ok, count = self._process_library(context, friend=True)
            total += count
            if not ok:
                return False, total

            previous = title
            self._click(context, NEXT_FRIEND, "下一个好友订单库")
            changed = False
            deadline = time.time() + 8.0
            while time.time() < deadline:
                image = self._shot(context)
                page = self._detect_page(context, image)
                if page == "own_order":
                    log.info("好友订单库遍历完成，已回到自主订单库")
                    return True, total
                if page == "friend_order":
                    current = self._order_title(context, image)
                    if not previous or (current and current != previous):
                        changed = True
                        break
                self._sleep(context, 0.4)
            if not changed:
                log.warning("切换下一个好友订单库超时")
                return False, total
        log.warning("好友遍历达到60页安全上限")
        return False, total

    def run(self, context, argv) -> bool:
        self.settings = self._read_settings()
        self._load_daily_state()
        log.info(
            "基建-订单库开始：构建消耗=%s 构建自动合成=%s 稀有星币=%s/%s 稀有技术点=%s/%s 当日好友去重=%d",
            sorted(self.settings["build_costs"]), self.settings["build_synth"],
            self.settings["rare_coin"], self.settings["rare_coin_synth"],
            self.settings["rare_tech"], self.settings["rare_tech_synth"],
            len(self.friend_completed),
        )
        try:
            if not self._ensure_own_order(context):
                return False
            own_ok, own_count = self._process_library(context, friend=False)
            if not own_ok:
                return False
            friends_ok, friend_count = self._visit_friends(context)
            if not friends_ok:
                return False
            log.info("基建-订单库完成：自主订单%d，好友订单%d", own_count, friend_count)
            return True
        except ActionStopped:
            log.info("检测到用户停止任务，基建-订单库立即停止")
            return False
        except Exception:
            log.exception("基建-订单库执行异常")
            return False
