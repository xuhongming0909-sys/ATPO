# AI-SUMMARY: run.py CLI 契约测试——64/32 位转交、schedule-json、交易日门、状态门与阶段分发
import contextlib
import io
import unittest
import unittest.mock as mock
from datetime import date

import run


def test_gui_command_relaunches_with_project_venv32(monkeypatch):
    calls = []

    class _P:
        returncode = 0

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _P()

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run.struct, "calcsize", lambda _fmt: 64)
    import pathlib

    monkeypatch.setattr(pathlib.Path, "is_file", lambda _self: True)
    try:
        run.ensure_command_runtime("ths-cycle", ["ths-cycle"])
    except SystemExit as exc:
        assert exc.code == 0
    assert calls and calls[0][0].endswith(r".venv32\Scripts\python.exe")


def test_non_gui_command_not_relaunched(monkeypatch):
    monkeypatch.setattr(run.struct, "calcsize", lambda _fmt: 64)
    run.ensure_command_runtime("calendar", ["calendar"])  # 不抛 SystemExit 即通过


def test_catchup_cli_parses_date_and_live(monkeypatch):
    monkeypatch.setattr(run, "ensure_command_runtime", lambda *_: None)
    seen = {}

    def fake_catch_up(day, **kw):
        seen.update(day=day, **kw)
        return {"catchup": {"status": "completed"}}

    monkeypatch.setattr("scheduler.catchup.catch_up", fake_catch_up)
    monkeypatch.setattr("scheduler.catchup.wait_network", lambda *_a, **_k: None)
    monkeypatch.setattr("shared.config.load_config", lambda: {"boot_login": {}})
    monkeypatch.setattr("sys.argv", ["run.py", "catch-up", "--date", "2026-10-17", "--live"])
    run.main()
    assert seen["day"] == "2026-10-17"
    assert seen["live"] is True


class CliContractTests(unittest.TestCase):
    def test_schedule_json_reads_config_schedule(self):
        with mock.patch("shared.config.load_config", return_value={
                "schedule": {"calendar_fetch": "08:30", "subscribe_time": "10:00",
                             "allotment_check_1": "22:00", "allotment_check_2": "08:00"},
                "execution": {}}):
            self.assertEqual(run._schedule_json(), {
                "calendar_fetch": "08:30", "subscribe_time": "10:00",
                "allotment_check_1": "22:00", "allotment_check_2": "08:00"})

    def test_schedule_json_rejects_invalid_time(self):
        from shared.errors import AutoIpoError

        with mock.patch("shared.config.load_config", return_value={"schedule": {
                "calendar_fetch": "8点", "subscribe_time": "10:00",
                "allotment_check_1": "22:00", "allotment_check_2": "08:00"}}):
            with self.assertRaises(AutoIpoError) as ctx:
                run._schedule_json()
        self.assertEqual(ctx.exception.code, "SCHEDULE_INVALID")

    def test_webui_command_not_exposed(self):
        out = io.StringIO()
        with mock.patch("sys.argv", ["run.py", "webui"]), contextlib.redirect_stderr(out):
            with self.assertRaises(SystemExit):
                run.main()
        help_out = io.StringIO()
        with mock.patch("sys.argv", ["run.py", "--help"]), contextlib.redirect_stdout(help_out):
            with self.assertRaises(SystemExit):
                run.main()
        self.assertNotIn("webui", help_out.getvalue())
        self.assertIn("schedule-json", help_out.getvalue())
        self.assertIn("ths-cycle", help_out.getvalue())

    def test_daily_report_skips_non_trading_day(self):
        with mock.patch.object(run, "ensure_command_runtime", lambda *_: None),              mock.patch("data_fetch.trading_days.is_trading_day", return_value=False),              mock.patch("scheduler.jobs.daily_report",
                        side_effect=AssertionError("非交易日不得抓取/推送")),              mock.patch("sys.argv", ["run.py", "daily-report", "--day", "2026-10-25"]):
            run.main()

    def test_daily_report_gate_blocks_completed(self):
        with mock.patch.object(run, "ensure_command_runtime", lambda *_: None),              mock.patch("data_fetch.trading_days.is_trading_day", return_value=True),              mock.patch.object(run, "_state_gate_skip", return_value=True),              mock.patch("scheduler.jobs.daily_report",
                        side_effect=AssertionError("状态门拦截后不得执行")),              mock.patch("sys.argv", ["run.py", "daily-report", "--day", "2026-10-17"]):
            run.main()

    def test_allotment_cli_uses_shared_idempotent_gate(self):
        seen = {}
        with mock.patch.object(run, "ensure_command_runtime", lambda *_: None),              mock.patch("scheduler.catchup.allotment_business_day", return_value="2026-10-17"),              mock.patch("scheduler.catchup.run_ths_cycle",
                        side_effect=lambda day, phase, **kw: seen.update(day=day, phase=phase, **kw) or {"allotment": {"status": "completed"}}),              mock.patch("shared.config.load_config", return_value={}),              mock.patch("sys.argv", ["run.py", "allotment"]):
            run.main()
        self.assertEqual(seen["day"], "2026-10-17")
        self.assertEqual(seen["phase"], "allotment")
        self.assertTrue(seen["allow_recheck"])


class ThsCycleCliTests(unittest.TestCase):
    def test_ths_cycle_is_gui_command(self):
        self.assertIn("ths-cycle", run.GUI_COMMANDS)
        self.assertIn("catch-up", run.GUI_COMMANDS)

    def test_ths_cycle_cli_dispatches_date_phase_live(self):
        seen = {}
        with mock.patch.object(run, "ensure_command_runtime", lambda *_: None),              mock.patch("scheduler.catchup.run_ths_cycle",
                        side_effect=lambda day, phase, **kw: seen.update(day=day, phase=phase, **kw) or {}),              mock.patch("shared.config.load_config", return_value={}),              mock.patch("sys.argv", ["run.py", "ths-cycle", "--date", "2026-10-17",
                                     "--phase", "subscribe", "--live"]):
            run.main()
        self.assertEqual(seen["day"], "2026-10-17")
        self.assertEqual(seen["phase"], "subscribe")
        self.assertTrue(seen["live"])

    def test_ths_cycle_cli_phase_defaults_to_all(self):
        seen = {}
        with mock.patch.object(run, "ensure_command_runtime", lambda *_: None),              mock.patch("scheduler.catchup.run_ths_cycle",
                        side_effect=lambda day, phase, **kw: seen.update(day=day, phase=phase, **kw) or {}),              mock.patch("shared.config.load_config", return_value={}),              mock.patch("sys.argv", ["run.py", "ths-cycle"]):
            run.main()
        self.assertEqual(seen["phase"], "all")
        self.assertEqual(seen["day"], date.today().isoformat())

    def test_ths_cycle_cli_fails_on_lifecycle_residual(self):
        with mock.patch.object(run, "ensure_command_runtime", lambda *_: None),              mock.patch("scheduler.catchup.run_ths_cycle", return_value={
                 "login": {"status": "completed"},
                 "lifecycle": {"status": "lifecycle_failed"},
             }),              mock.patch("shared.config.load_config", return_value={}),              mock.patch("sys.argv", ["run.py", "ths-cycle", "--phase", "login"]):
            with self.assertRaises(SystemExit) as ctx:
                run.main()
        self.assertEqual(ctx.exception.code, 1)
