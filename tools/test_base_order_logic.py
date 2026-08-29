# -*- coding: utf-8 -*-
"""Offline checks for BaseExchangeTask decisions; never sends controller input."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

from base_order_flow import BaseOrderFlow, CARDS  # noqa: E402


def test_friend_signature_ignores_reward_level():
    first = {
        "kind": "build", "rare": False, "cost": 18,
        "text": "奖励构建订单IVX2稀有黑匣X18",
    }
    second = {
        "kind": "build", "rare": False, "cost": 18,
        "text": "奖励构建订单IX1稀有黑匣X18",
    }
    assert BaseOrderFlow._order_signature(first) == "build:normal:18"
    assert BaseOrderFlow._order_signature(first) == BaseOrderFlow._order_signature(second)


def test_sparse_friend_library_only_returns_detected_cards():
    flow = BaseOrderFlow()
    text_by_roi = {
        tuple(CARDS[0]["roi"]): "稀有技术点订单IVX120000数据硬盘X10可交付",
        tuple(CARDS[0]["cost_roi"]): "X10可交付",
        tuple(CARDS[5]["roi"]): "构建订单IX1稀有黑匣X8可交付",
        tuple(CARDS[5]["cost_roi"]): "X8可交付",
    }
    flow._ocr = lambda _context, _image, roi, _node="BaseScreenText": text_by_roi.get(tuple(roi), "")
    flow._color_ratio = lambda _image, _roi, _kind: 0.0

    orders = flow._scan_orders(None, object())

    assert len(orders) == 2
    assert [order["index"] for order in orders] == [0, 5]
    assert orders[0]["kind"] == "tech" and orders[0]["rare"]
    assert orders[1]["kind"] == "build" and orders[1]["cost"] == 8


def test_default_eligibility_and_friend_daily_deduplication():
    flow = BaseOrderFlow()
    flow.settings = {
        "build_costs": {6, 8, 16},
        "rare_coin": False,
        "rare_tech": True,
    }
    build = {"kind": "build", "cost": 8, "rare": False, "signature": "build:normal:8"}
    rare_tech = {"kind": "tech", "cost": 10, "rare": True, "signature": "tech:rare:10"}
    assert flow._eligible(build, friend=False)
    assert flow._eligible(rare_tech, friend=True)
    flow.friend_completed.add("tech:rare:10")
    assert not flow._eligible(rare_tech, friend=True)
    assert flow._eligible(rare_tech, friend=False)


if __name__ == "__main__":
    tests = [value for name, value in globals().items() if name.startswith("test_")]
    for test in tests:
        test()
    print(f"BASE_ORDER_LOGIC_OK ({len(tests)} tests)")
