# -*- coding: utf-8 -*-
"""Handle the launch screens according to the recorder's special annotations.

Recognition only checks small, stable regions around marked controls. It never
waits for a full-screen or OCR match.
"""
import json
import logging
import subprocess
import time
from pathlib import Path

from maa.custom_action import CustomAction

from navigation import BACK_BUTTON, IDLE_MAIN_WAKE, is_idle_main_ui, is_main_ui
from stop_guard import ActionStopped, ensure_running


log = logging.getLogger("startgame")
log.setLevel(logging.INFO)
if not log.handlers:
    log.addHandler(logging.StreamHandler())

# record/20260825-121545-794c23 special annotations (1920x1080)
START_BUTTON = (963, 726)
NOTICE_DONT_SHOW = (1608, 943)
NOTICE_CLOSE = (1815, 146)
DAILY_SIGN_IN = (1746, 906)
DAILY_REWARD_DISMISS = (1071, 929)
DAILY_BACK = BACK_BUTTON
AD_DONT_SHOW = (1024, 984)
AD_CLOSE = (1676, 220)

ROI_START = [850, 675, 225, 105]
ROI_NOTICE_CLOSE = [1785, 115, 70, 70]
ROI_NOTICE_OPTION = [1565, 905, 305, 75]
ROI_SIGN_IN = [1625, 855, 250, 105]
ROI_AD_CLOSE = [1640, 180, 80, 80]
ROI_AD_BUY = [1090, 835, 320, 110]
ADB = r"E:\MuMuPlayer-12.0\shell\adb.exe"
GAME_PACKAGE = "com.megagame.crosscore"
GAME_ACTIVITY = "com.megagame.crosscore/com.mjsdk.app.MJUnityActivity"
INSTANCE_CONFIG = Path(r"E:\LAA\MaaBoilerplate\gui\config\instances\default.json")


class StartGameFlow(CustomAction):
    def _shot(self, ctx):
        ensure_running(ctx)
        return ctx.tasker.controller.post_screencap().wait().get()

    def _click(self, ctx, point, label):
        ensure_running(ctx)
        ctx.tasker.controller.post_click(*point).wait()
        log.info("按录制标注点击%s坐标(%d,%d)", label, point[0], point[1])

    @staticmethod
    def _adb_serials(context):
        ensure_running(context)
        serials = []
        try:
            data = json.loads(INSTANCE_CONFIG.read_text(encoding="utf-8"))
            configured = str((data.get("AdbDevice") or {}).get("AdbSerial") or "").strip()
            if configured:
                serials.append(configured)
        except Exception as exc:
            log.warning("读取MFA当前ADB地址失败：%s", exc)

        try:
            result = subprocess.run(
                [ADB, "devices"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=3,
            )
            ensure_running(context)
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    serials.append(parts[0])
        except ActionStopped:
            raise
        except Exception as exc:
            log.warning("枚举ADB在线设备失败：%s", exc)

        serials.extend(["127.0.0.1:16416", "127.0.0.1:16417", "emulator-5556"])
        return list(dict.fromkeys(serial for serial in serials if serial))

    @classmethod
    def _game_is_foreground_on(cls, context, serial):
        ensure_running(context)
        try:
            result = subprocess.run(
                [ADB, "-s", serial, "shell", "dumpsys", "activity", "activities"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=3,
            )
            ensure_running(context)
            return any(
                ("topResumedActivity" in line or "mResumedActivity" in line)
                and GAME_PACKAGE in line
                for line in result.stdout.splitlines()
            )
        except ActionStopped:
            raise
        except Exception:
            return False

    @classmethod
    def _game_is_foreground(cls, context):
        for serial in cls._adb_serials(context):
            if cls._game_is_foreground_on(context, serial):
                log.info("已通过ADB设备%s确认交错战线处于前台", serial)
                return True
        return False

    @classmethod
    def _ensure_game_foreground(cls, context):
        """Launch the game even when MFA reused an already-connected controller."""
        serials = cls._adb_serials(context)
        for serial in serials:
            ensure_running(context)
            if cls._game_is_foreground_on(context, serial):
                log.info("交错战线已在设备%s前台，继续识别登录流程", serial)
                return True
            try:
                state = subprocess.run(
                    [ADB, "-s", serial, "get-state"],
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=3,
                )
                if state.returncode != 0 or "device" not in state.stdout:
                    continue
                log.info("设备%s在线但游戏未在前台，正在启动交错战线", serial)
                subprocess.run(
                    [
                        ADB, "-s", serial, "shell", "monkey", "-p", GAME_PACKAGE,
                        "-c", "android.intent.category.LAUNCHER", "1",
                    ],
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=10,
                )
                for _ in range(20):
                    ensure_running(context)
                    time.sleep(0.5)
                    if cls._game_is_foreground_on(context, serial):
                        log.info("已启动交错战线，等待开始游戏页面")
                        return True
                subprocess.run(
                    [ADB, "-s", serial, "shell", "am", "start", "-n", GAME_ACTIVITY],
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=10,
                )
                for _ in range(20):
                    ensure_running(context)
                    time.sleep(0.5)
                    if cls._game_is_foreground_on(context, serial):
                        log.info("已通过Activity启动交错战线，等待开始游戏页面")
                        return True
            except ActionStopped:
                raise
            except Exception as exc:
                log.warning("通过设备%s启动交错战线失败：%s", serial, exc)
        log.error("未能在当前MuMu设备启动交错战线")
        return False

    def _ratio(self, img, roi, kind):
        """Measure broad color structure in one annotated key region."""
        try:
            x, y, w, h = roi
            crop = img[y:y + h:4, x:x + w:4]
            if crop.size == 0:
                return 0.0
            c0 = crop[:, :, 0].astype("int16")
            c1 = crop[:, :, 1].astype("int16")
            c2 = crop[:, :, 2].astype("int16")
            if kind == "white":
                mask = (c0 > 205) & (c1 > 205) & (c2 > 205)
            elif kind == "orange":
                rgb = (c0 > 175) & (c1 > 95) & (c1 < 225) & (c2 < 150)
                bgr = (c2 > 175) & (c1 > 95) & (c1 < 225) & (c0 < 150)
                mask = rgb | bgr
            elif kind == "cyan":
                rgb = (c0 < 120) & (c1 > 145) & (c2 > 130)
                bgr = (c2 < 120) & (c1 > 145) & (c0 > 130)
                mask = rgb | bgr
            else:
                mask = (c0 < 70) & (c1 < 70) & (c2 < 70)
            return float(mask.mean())
        except Exception as e:
            log.warning("关键区域颜色检测失败：%s", e)
            return 0.0

    def _is_notice(self, img):
        close_white = self._ratio(img, ROI_NOTICE_CLOSE, "white")
        option_orange = self._ratio(img, ROI_NOTICE_OPTION, "orange")
        return close_white > 0.035 and option_orange > 0.018

    def _is_daily_sign_in(self, img):
        return self._ratio(img, ROI_SIGN_IN, "orange") > 0.10

    def _is_purchase_ad(self, img):
        close_white = self._ratio(img, ROI_AD_CLOSE, "white")
        buy_cyan = self._ratio(img, ROI_AD_BUY, "cyan")
        return close_white > 0.025 and buy_cyan > 0.06

    def _is_start_screen(self, context, img):
        """Require both the marked local shape and start text to reject weak lookalikes."""
        key = context.run_recognition("SG_StartKey", img)
        text = context.run_recognition("SG_StartClick", img)
        return bool(key and key.hit and text and text.hit)

    def _is_main(self, context, img):
        # Character models and the large attack control can change. Require two
        # adjacent, fixed bottom navigation controls instead.
        return is_main_ui(context, img)

    def run(self, context, argv) -> bool:
        try:
            return self._run(context, argv)
        except ActionStopped:
            log.info("检测到MFA停止状态，开始游戏立即停止且不再执行点击")
            return False

    def _run(self, context, argv) -> bool:
        if not self._ensure_game_foreground(context):
            return False

        deadline = time.time() + 120
        last_action = 0.0
        last_start_click = 0.0
        start_clicks = 0
        start_screen_hits = 0
        handled = set()

        while time.time() < deadline:
            ensure_running(context)
            img = self._shot(context)

            if is_idle_main_ui(context, img):
                self._click(context, IDLE_MAIN_WAKE, "主界面待机画面空白处")
                time.sleep(1.0)
                continue

            is_start_screen = self._is_start_screen(context, img)

            if self._is_notice(img):
                self._click(context, NOTICE_DONT_SHOW, "公告的“今天不再提示”")
                time.sleep(0.35)
                self._click(context, NOTICE_CLOSE, "公告关闭按钮")
                handled.add("notice")
                last_action = time.time()
                time.sleep(1.2)
                continue

            if self._is_daily_sign_in(img):
                self._click(context, DAILY_SIGN_IN, "每日签到")
                time.sleep(2.0)
                self._click(context, DAILY_REWARD_DISMISS, "签到奖励弹窗空白处")
                time.sleep(0.8)
                self._click(context, DAILY_BACK, "签到页左上返回键")
                handled.add("daily_sign_in")
                last_action = time.time()
                time.sleep(1.2)
                continue

            if self._is_purchase_ad(img):
                self._click(context, AD_DONT_SHOW, "礼包广告的“今天不再提示”")
                time.sleep(0.35)
                self._click(context, AD_CLOSE, "礼包广告关闭按钮")
                handled.add("purchase_ad")
                last_action = time.time()
                time.sleep(1.2)
                continue

            start_screen_hits = start_screen_hits + 1 if is_start_screen else 0
            can_click_start = (
                start_clicks == 0
                or (
                    start_clicks < 4
                    and start_screen_hits >= 2
                    and time.time() - last_start_click >= 7
                )
            )
            if is_start_screen and can_click_start:
                self._click(context, START_BUTTON, "开始游戏")
                handled.add("start_button")
                last_action = time.time()
                last_start_click = last_action
                start_clicks += 1
                start_screen_hits = 0
                time.sleep(1.0)
                continue

            if self._is_main(context, img):
                done = ", ".join(sorted(handled)) or "无"
                log.info("已到主界面；已处理开屏项目：%s", done)
                return True

            time.sleep(0.45)

        log.warning("120秒内未明确识别到主界面；停止任务，避免在登录或未知页面提前完成。已处理：%s", handled)
        return False
