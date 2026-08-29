# -*- coding: utf-8 -*-
"""Run one WeeklyTask against the same resource and action used by MFA."""
import sys
import time

from maa.controller import AdbController
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit


ROOT = r"E:/LAA/MaaBoilerplate"
sys.path.insert(0, rf"{ROOT}/agent")

from weekly_complete import WeeklyFlow  # noqa: E402
from startgame_flow import StartGameFlow  # noqa: E402
from navigation import BACK_BUTTON, recognize_main_controls  # noqa: E402


class ResumeWeeklyMap(WeeklyFlow):
    """Verification-only action for continuing an already opened fresh map."""

    def run(self, context, argv):
        image = self._shot(context)
        if not self._is_map_ready(image):
            print("RESUME_MAP_NOT_READY", flush=True)
            return False
        identified = self._identify_map(context, image)
        if identified is None:
            return False
        case_id, camera_done = identified
        print("RESUME_CASE", case_id, flush=True)
        self._run_map_route(context, case_id, camera_done)
        return self._finish_battle(context)


class ContinueCase4(WeeklyFlow):
    """Verification-only action after the first two case-4 moves."""

    def run(self, context, argv):
        if not self._is_map_ready(self._shot(context)):
            return False
        self._run_case_moves(context, 4, start_index=2)
        return self._finish_battle(context)


class DiagnoseWeeklyPage(WeeklyFlow):
    """Read the current weekly page without performing any input."""

    def run(self, context, argv):
        image = self._shot(context)
        print("WEEKLY_PAGE", self._detect_page(context, image), flush=True)
        print("WEEKLY_TEXT", self._screen_text(context, image), flush=True)
        hit, detail = self._recognized(context, "WeeklyBossMarker", image)
        print("WEEKLY_BOSS", hit, detail.box if detail else None, flush=True)
        spawn_hit, spawn_detail = self._recognized(context, "WeeklySpawnMarker", image)
        print("WEEKLY_SPAWN", spawn_hit, spawn_detail.box if spawn_detail else None, flush=True)
        body_hit, body_detail = self._recognized(context, "WeeklySpawnCharacter", image)
        print("WEEKLY_SPAWN_BODY", body_hit, body_detail.box if body_detail else None, flush=True)
        anchor_hit, anchor_detail = self._recognized(context, "WeeklyRouteAnchor", image)
        print("WEEKLY_ROUTE_ANCHOR", anchor_hit, anchor_detail.box if anchor_detail else None, flush=True)
        for node in ("NavMainBase", "NavMainTask"):
            hit, detail = self._recognized(context, node, image)
            score = self._recognition_score(detail) if detail is not None else 0.0
            print("MAIN_UI", node, hit, detail.box if detail else None, score, flush=True)
        print("MAIN_CONTROLS", recognize_main_controls(context, image), flush=True)
        return True


class NavigateWeeklyOnly(WeeklyFlow):
    """Verification-only handoff test that stops before selecting or fighting."""

    def run(self, context, argv):
        page = self._navigate_to_weekly(context)
        print("NAVIGATE_WEEKLY_PAGE", page, flush=True)
        return page in ("boss_choice", "battle_prep")


class FinishStuckBoss(WeeklyFlow):
    """Verification-only recovery for a route that ended beside the boss."""

    def run(self, context, argv):
        image = self._shot(context)
        if not self._is_map_ready(image) or not self._click_visible_boss(context, image):
            print("STUCK_BOSS_NOT_READY", flush=True)
            return False
        return self._finish_battle(context)


class FinishCurrentBattle(WeeklyFlow):
    """Verification-only settlement recovery from battle or result pages."""

    def run(self, context, argv):
        return self._finish_battle(context)


class ResumeKnownCase(WeeklyFlow):
    """Verification-only recovery when the case is already known from the log."""

    def __init__(self, case_id):
        super().__init__()
        self.case_id = case_id

    def run(self, context, argv):
        if not self._is_map_ready(self._shot(context)):
            print("RESUME_KNOWN_CASE_NOT_READY", self.case_id, flush=True)
            return False
        if not self._run_map_route(context, self.case_id):
            return False
        return self._finish_battle(context)


class VerificationWeeklyFlow(WeeklyFlow):
    """Skip already-covered random cases to shorten four-case verification."""

    def __init__(self):
        super().__init__()
        self.completed_cases = set()
        self.skipped_duplicate = False

    @staticmethod
    def _stop_when_rewards_full():
        # Verification must keep sampling maps after the live account reaches 600/600.
        return False

    def run(self, context, argv):
        self.skipped_duplicate = False
        return super().run(context, argv)

    def _run_map_route(self, context, case_id, camera_done=0):
        if case_id not in self.completed_cases:
            return super()._run_map_route(context, case_id, camera_done)
        print("VERIFY_DUPLICATE_EXIT", case_id, flush=True)
        self._click(context, BACK_BUTTON, "重复情况左上返回键")
        time.sleep(0.8)
        self._click(context, (1205, 675), "重复情况撤退确认")
        time.sleep(3.0)
        self.skipped_duplicate = True
        return False


def main():
    Toolkit.init_option(ROOT)
    controller = AdbController(
        adb_path=r"E:\MuMuPlayer-12.0\shell\adb.exe",
        address="127.0.0.1:16416",
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
    weekly_flow = WeeklyFlow()
    verification_flow = VerificationWeeklyFlow()
    resource.register_custom_action("weekly_flow", weekly_flow)
    resource.register_custom_action("weekly_verify_flow", verification_flow)
    resource.register_custom_action("weekly_resume", ResumeWeeklyMap())
    resource.register_custom_action("weekly_case4_tail", ContinueCase4())
    resource.register_custom_action("weekly_diagnose_page", DiagnoseWeeklyPage())
    resource.register_custom_action("weekly_navigate_only", NavigateWeeklyOnly())
    resource.register_custom_action("weekly_finish_stuck_boss", FinishStuckBoss())
    resource.register_custom_action("weekly_finish_current", FinishCurrentBattle())
    for case_id in range(1, 5):
        resource.register_custom_action(
            f"weekly_resume_case_{case_id}", ResumeKnownCase(case_id)
        )
    resource.register_custom_action("startgame", StartGameFlow())
    resource.post_bundle(rf"{ROOT}/gui/resource").wait()
    print("RESOURCE", resource.loaded, flush=True)
    if not resource.loaded:
        return 3

    tasker = Tasker()
    tasker.bind(resource, controller)
    if "--resume-map" in sys.argv:
        detail = tasker.post_task(
            "WeeklyTask",
            {"WeeklyTask": {"custom_action": "weekly_resume"}},
        ).wait().get()
        print("RESUME_DETAIL", detail, flush=True)
        return 0 if detail is not None else 6
    if "--case4-tail" in sys.argv:
        detail = tasker.post_task(
            "WeeklyTask",
            {"WeeklyTask": {"custom_action": "weekly_case4_tail"}},
        ).wait().get()
        print("CASE4_TAIL_DETAIL", detail, flush=True)
        return 0 if detail is not None else 7
    if "--diagnose-page" in sys.argv:
        detail = tasker.post_task(
            "WeeklyTask",
            {"WeeklyTask": {"custom_action": "weekly_diagnose_page"}},
        ).wait().get()
        print("DIAGNOSE_DETAIL", detail, flush=True)
        return 0 if detail is not None else 8
    if "--navigate-only" in sys.argv:
        detail = tasker.post_task(
            "WeeklyTask",
            {"WeeklyTask": {"custom_action": "weekly_navigate_only"}},
        ).wait().get()
        print("NAVIGATE_ONLY_DETAIL", detail, flush=True)
        return 0 if detail is not None else 18
    if "--finish-stuck-boss" in sys.argv:
        detail = tasker.post_task(
            "WeeklyTask",
            {"WeeklyTask": {"custom_action": "weekly_finish_stuck_boss"}},
        ).wait().get()
        print("FINISH_STUCK_BOSS_DETAIL", detail, flush=True)
        return 0 if detail is not None else 9
    if "--finish-current" in sys.argv:
        detail = tasker.post_task(
            "WeeklyTask",
            {"WeeklyTask": {"custom_action": "weekly_finish_current"}},
        ).wait().get()
        print("FINISH_CURRENT_DETAIL", detail, flush=True)
        return 0 if detail is not None else 10
    if "--verify-all-cases" in sys.argv:
        completed = {
            case_id for case_id in range(1, 5)
            if f"--verified-case-{case_id}" in sys.argv
        }
        print("VERIFY_INITIAL_COMPLETED", sorted(completed), flush=True)
        for run_index in range(1, 41):
            verification_flow.completed_cases = set(completed)
            detail = tasker.post_task(
                "WeeklyTask",
                {"WeeklyTask": {"custom_action": "weekly_verify_flow"}},
            ).wait().get()
            case_id = verification_flow.last_case_id
            if verification_flow.skipped_duplicate:
                print(
                    "VERIFY_RUN",
                    run_index,
                    "CASE",
                    case_id,
                    "SKIPPED_DUPLICATE",
                    "COMPLETED",
                    sorted(completed),
                    flush=True,
                )
                continue
            succeeded = verification_flow.last_run_success and detail is not None
            if succeeded and case_id in range(1, 5):
                completed.add(case_id)
            print(
                "VERIFY_RUN",
                run_index,
                "CASE",
                case_id,
                "SUCCESS",
                succeeded,
                "COMPLETED",
                sorted(completed),
                flush=True,
            )
            if completed == {1, 2, 3, 4}:
                print("VERIFY_ALL_CASES_OK", flush=True)
                return 0
            if not succeeded:
                print("VERIFY_RESTART_AFTER_FAILURE", run_index, flush=True)
                time.sleep(2.0)
                continue
        print("VERIFY_ALL_CASES_INCOMPLETE", sorted(completed), flush=True)
        return 21
    for case_id in range(1, 5):
        if f"--resume-case-{case_id}" in sys.argv:
            detail = tasker.post_task(
                "WeeklyTask",
                {"WeeklyTask": {"custom_action": f"weekly_resume_case_{case_id}"}},
            ).wait().get()
            print("RESUME_KNOWN_CASE_DETAIL", case_id, detail, flush=True)
            return 0 if detail is not None else 10 + case_id
    start_detail = tasker.post_task("StartGameTask").wait().get()
    print("START_GAME", start_detail, flush=True)
    if start_detail is None:
        return 4
    detail = tasker.post_task("WeeklyTask").wait().get()
    print("DETAIL", detail, flush=True)
    if detail is None:
        return 5
    print("STATUS", detail.status, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
