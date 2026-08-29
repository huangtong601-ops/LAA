# -*- coding: utf-8 -*-
"""Reusable chip-detail reader built from the chip-filter 1.0/2.0 recordings."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import time

from maa.custom_action import CustomAction

from navigation import HOME_BUTTON, is_idle_main_ui, is_main_ui
from stop_guard import ActionStopped, ensure_running


log = logging.getLogger("laa.chip_filter")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULT_FILE = PROJECT_ROOT / "config" / "chip_scan_latest.json"

MAIN_SKILLS = (
    "穿甲", "切割", "征服", "重击",
    "支援", "精力", "蓄能", "收割",
    "屏障", "铁壁", "灵巧", "暴怒",
    "致命", "腐蚀", "集中", "金刚",
    "痛击", "扩大", "物攻", "能量",
    "装填", "光幕", "钝化", "特防",
    "神威", "神力", "神速", "振奋",
    "消除", "重伤", "连击", "乘风",
    "反击", "协击", "引爆",
)
SUB_SKILLS = ("攻击", "耐久", "防御", "速度", "瞄准", "暴伤", "命中", "坚韧")
ALL_SKILLS = MAIN_SKILLS + SUB_SKILLS

WAREHOUSE_BUTTON = (1723, 63)  # 芯片筛选1.0 图1“仓库按钮”标注中心。
CHIP_TAB = (1800, 70)          # 图4“芯片区”标注中心。
DETAIL_CLOSE_BLANK = (300, 700)
DETAIL_LOCK_TOGGLE = (1207, 158)  # 芯片筛选2.0“上锁/弃置键”标注中心。

# The fourth row is cut off by the bottom edge. Read the three complete rows first;
# later full-inventory scanning can reuse these columns after deterministic paging.
CHIP_COLUMNS = (169, 421, 673, 925, 1177, 1429)
CHIP_ROWS = (270, 520, 765)
VISIBLE_SLOTS = tuple(
    {"index": row * 6 + col + 1, "point": (x, y)}
    for row, y in enumerate(CHIP_ROWS)
    for col, x in enumerate(CHIP_COLUMNS)
)

DETAIL_NAME_ROIS = (
    [790, 308, 225, 56],
    [790, 383, 225, 56],
    [790, 458, 225, 56],
    [790, 533, 225, 56],
)
DETAIL_LEVEL_ROIS = (
    [1038, 308, 130, 56],
    [1038, 383, 130, 56],
    [1038, 458, 130, 56],
    [1038, 533, 130, 56],
)


def normalize_ocr(text):
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", str(text or ""))


def parse_level(text):
    """Extract the only legal chip-skill levels without accepting unrelated digits."""
    normalized = normalize_ocr(text)
    match = re.search(r"(?:等级)?([123])$", normalized)
    return int(match.group(1)) if match else None


def validate_chip_detail(rows):
    """Convert four OCR rows into a typed chip detail, or reject partial reads."""
    if len(rows) != 4:
        return None
    names = [row[0] for row in rows]
    levels = [row[1] for row in rows]
    if names[0] not in MAIN_SKILLS or any(name not in SUB_SKILLS for name in names[1:]):
        return None
    if any(level not in (1, 2, 3) for level in levels):
        return None
    return {
        "main_skill": {"name": names[0], "level": levels[0]},
        "sub_skills": [
            {"name": name, "level": level}
            for name, level in zip(names[1:], levels[1:])
        ],
    }


class ChipFilterFlow(CustomAction):
    """Navigate to the chip area and read its first 18 complete slots in grid order."""

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

    @staticmethod
    def _ocr_results(context, image, node, roi, choices=None):
        override = {node: {"roi": roi, "threshold": 0.2}}
        if choices is not None:
            override[node]["text"] = list(choices)
        detail = context.run_recognition(node, image, pipeline_override=override)
        if not detail or not detail.hit:
            return []
        return [str(getattr(item, "text", "")) for item in (detail.all_results or [])]

    def _page_text(self, context, image, roi):
        try:
            return "".join(self._ocr_results(context, image, "ChipPageText", roi))
        except Exception:
            return ""

    def _is_chip_page(self, context, image):
        text = normalize_ocr(self._page_text(context, image, [380, 20, 1510, 105]))
        return "筛选" in text and "芯片" in text

    def _is_warehouse(self, context, image):
        text = normalize_ocr(self._page_text(context, image, [1370, 20, 520, 105]))
        return "物品" in text or "芯片" in text

    def _is_detail_open(self, context, image):
        try:
            title = normalize_ocr(self._page_text(context, image, [850, 120, 360, 100]))
            if "芯片" in title:
                return True
            first = self._read_skill_name(context, image, 0)
            return first in MAIN_SKILLS
        except Exception:
            return False

    def _ensure_chip_page(self, context):
        for _ in range(12):
            image = self._shot(context)
            if self._is_chip_page(context, image):
                return True
            if is_idle_main_ui(context, image):
                self._click(context, (960, 540), "唤醒主界面")
            elif is_main_ui(context, image):
                self._click(context, WAREHOUSE_BUTTON, "主界面仓库按钮")
            elif self._is_warehouse(context, image):
                self._click(context, CHIP_TAB, "仓库芯片区")
            else:
                self._click(context, HOME_BUTTON, "主界面键")
            self._sleep(context, 0.9)
        return False

    def _read_skill_name(self, context, image, row):
        choices = MAIN_SKILLS if row == 0 else SUB_SKILLS
        texts = self._ocr_results(
            context, image, "ChipSkillName", DETAIL_NAME_ROIS[row], choices
        )
        normalized = [normalize_ocr(text) for text in texts]
        for choice in choices:
            if any(choice in text for text in normalized):
                return choice
        return None

    def _read_skill_level(self, context, image, row):
        texts = self._ocr_results(
            context, image, "ChipSkillLevel", DETAIL_LEVEL_ROIS[row]
        )
        for text in texts:
            level = parse_level(text)
            if level is not None:
                return level
        return None

    def _read_detail(self, context):
        readings = []
        for _ in range(4):
            image = self._shot(context)
            rows = [
                (self._read_skill_name(context, image, row),
                 self._read_skill_level(context, image, row))
                for row in range(4)
            ]
            detail = validate_chip_detail(rows)
            if detail:
                readings.append(detail)
                if len(readings) >= 2 and readings[-1] == readings[-2]:
                    return detail
            self._sleep(context, 0.18)
        return readings[-1] if readings else None

    def _save_results(self, results):
        RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
        RESULT_FILE.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "source": "warehouse_first_view",
                    "scan_order": "left_to_right_top_to_bottom",
                    "lock_toggle": {"x": DETAIL_LOCK_TOGGLE[0], "y": DETAIL_LOCK_TOGGLE[1]},
                    "chips": results,
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

    def run(self, context, argv) -> bool:
        try:
            if not self._ensure_chip_page(context):
                log.warning("无法进入仓库芯片区，停止读取")
                return False

            results = []
            for slot in VISIBLE_SLOTS:
                self._click(context, slot["point"], "第%d个芯片栏位" % slot["index"])
                self._sleep(context, 0.32)
                image = self._shot(context)
                if not self._is_detail_open(context, image):
                    log.info("栏位%d未打开芯片详情，按空栏位处理", slot["index"])
                    continue

                detail = self._read_detail(context)
                if detail:
                    detail["slot"] = slot["index"]
                    results.append(detail)
                    log.info(
                        "芯片%d：主技能=%s%d，副技能=%s",
                        slot["index"],
                        detail["main_skill"]["name"],
                        detail["main_skill"]["level"],
                        "、".join(
                            "%s%d" % (item["name"], item["level"])
                            for item in detail["sub_skills"]
                        ),
                    )
                else:
                    log.warning("栏位%d详情未能稳定读取，已跳过且不执行锁定操作", slot["index"])

                self._click(context, DETAIL_CLOSE_BLANK, "详情外空白处")
                self._sleep(context, 0.22)

            self._save_results(results)
            log.info("芯片首屏读取完成：成功%d/%d，结果=%s", len(results), len(VISIBLE_SLOTS), RESULT_FILE)
            return True
        except ActionStopped:
            log.info("检测到用户停止任务，芯片读取立即停止且不再点击")
            return True
        except Exception as exc:
            log.exception("芯片详细信息读取失败：%s", exc)
            return False
