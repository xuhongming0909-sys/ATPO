# AI-SUMMARY: CLI 统一入口——64/32 位运行时选择、任务状态记录、非交易日门与错过后补
import argparse
import json
import re
import struct
import subprocess
import sys
from datetime import date
from pathlib import Path

from shared.errors import AutoIpoError

# 需要 32 位 .venv32 的 GUI 命令（涉及 pywin32/jqktrader 券商客户端自动化）
GUI_COMMANDS = {"catch-up", "ths-cycle"}


def ensure_command_runtime(command: str, argv: list[str]) -> None:
    """GUI 命令自动转交项目 .venv32，避免用户必须记住 32 位解释器。"""
    if command not in GUI_COMMANDS or struct.calcsize("P") * 8 == 32:
        return
    from shared.paths import PROJECT_ROOT

    python32 = PROJECT_ROOT / ".venv32" / "Scripts" / "python.exe"
    if not python32.is_file():
        raise AutoIpoError(
            "ENV32_MISSING",
            "GUI 命令需要项目 .venv32（32 位 Python 3.11）",
            "运行 powershell -ExecutionPolicy Bypass -File scheduler\\setup.ps1",
            {"path": str(python32)},
        )
    proc = subprocess.run([str(python32), str(Path(__file__).resolve()), *argv], check=False)
    raise SystemExit(proc.returncode)


for _stream in (sys.stdout, sys.stderr):
    _stream.reconfigure(encoding="utf-8", errors="replace")


def _record_cli_task(task: str, day: str, status: str, receipt_status: str, mode: str,
                     payload, error: Exception | str = "") -> None:
    from shared.task_state import TaskStateStore

    TaskStateStore().record(task, day, status, receipt_status=receipt_status,
                            mode=mode, payload=payload, error=error)


SCHEDULE_KEYS = ("calendar_fetch", "subscribe_time", "allotment_check_1", "allotment_check_2")


def _schedule_json() -> dict:
    """只读输出 schedule 时间；scheduler/register_tasks.ps1 的唯一时间来源。"""
    from shared.config import load_config

    cfg = load_config()
    schedule = cfg.get("schedule") or {}
    out = {}
    for key in SCHEDULE_KEYS:
        value = str(schedule.get(key, "")).strip()
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
            raise AutoIpoError(
                "SCHEDULE_INVALID",
                f"schedule.{key} 必须是 HH:MM",
                "在 config/config.yaml 的 schedule 中修正时间",
                {"key": key, "value": value},
            )
        out[key] = value
    return out


def _state_gate_skip(task: str, day: str, mode: str) -> bool:
    """直接计划任务与 catch-up 共用 TaskStateStore 幂等状态门。"""
    from shared.task_state import TaskStateStore

    return TaskStateStore().should_skip(task, day, mode) is not None


def main() -> None:
    parser = argparse.ArgumentParser(prog="auto-ipo", description="自动打新系统（单同花顺切户模式）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("calendar", help="抓取某日打新日历并输出 JSON")
    sub.add_parser("daily-report", help="抓取当日日历并推送（非交易日自动跳过）")
    sub.add_parser("notify-test", help="发送一条 Server酱 通道测试消息")
    sub.add_parser("doctor", help="只读诊断：依赖、配置、DPAPI、客户端路径")

    p_cycle = sub.add_parser("ths-cycle", help="同花顺切户周期任务：按阶段登录/申购/中签，共用任务状态门")
    p_cycle.add_argument("--date", default=None, help="业务日期 YYYY-MM-DD，默认今天")
    p_cycle.add_argument("--phase", default="all", choices=["login", "subscribe", "allotment", "all"],
                         help="执行阶段，默认 all")
    p_cycle.add_argument("--live", action="store_true", help="实盘申购（需 config execution.mode=live 双重确认）")
    p_cycle.add_argument("--force-retry", action="store_true",
                         help="显式允许本轮重复提交/绕过已完成状态门；仅限人工授权测试")

    p_allot = sub.add_parser("allotment", help="中签查询：归属最近申购业务日，有中签才推送")
    p_catch = sub.add_parser("catch-up", help="联网后补当日错过的日历推送、窗口内申购和中签查询")
    p_catch.add_argument("--date", default=None, help="业务日期 YYYY-MM-DD，默认今天")
    p_catch.add_argument("--live", action="store_true", help="补做真实申购（需 config execution.mode=live；中签查询始终只读）")

    sub.add_parser("schedule-json", help="只读输出 config schedule 时间 JSON（计划任务注册唯一时间来源）")
    for name in ("calendar", "daily-report"):
        sub.choices[name].add_argument("--day", default=None, help="YYYY-MM-DD，默认今天")
    args = parser.parse_args()
    ensure_command_runtime(args.cmd, sys.argv[1:])

    if args.cmd == "calendar":
        from data_fetch.calendar import fetch_calendar_for

        day = args.day or date.today().isoformat()
        print(json.dumps(fetch_calendar_for(day), ensure_ascii=False, indent=2))
    elif args.cmd == "schedule-json":
        print(json.dumps(_schedule_json(), ensure_ascii=False))
    elif args.cmd == "notify-test":
        from notification import serverchan

        result = serverchan.send("自动打新 · 通道测试", "notify-test 推送成功。")
        print("推送成功, pushid:", result.get("data", {}).get("pushid"))
    elif args.cmd == "daily-report":
        from scheduler.jobs import daily_report

        day = args.day or date.today().isoformat()
        from data_fetch.trading_days import is_trading_day
        if is_trading_day(day) is False:
            print(json.dumps({"task": "daily_report", "date": day, "status": "skipped_non_trading"},
                             ensure_ascii=False))
            return
        if _state_gate_skip("daily_report", day, "live"):
            print(json.dumps({"task": "daily_report", "date": day, "status": "skipped_completed"},
                             ensure_ascii=False))
            return
        try:
            messages = daily_report(day=day)
            receipt = "sent" if messages else "not_required"
            _record_cli_task("daily_report", day, "completed", receipt, "live",
                             {"message_count": len(messages)})
        except Exception as exc:
            _record_cli_task("daily_report", day, "retryable", "failed", "live", None, exc)
            raise
        for title, body in messages:
            print(title)
            print(body)
            print()
    elif args.cmd == "allotment":
        from scheduler.catchup import allotment_business_day, run_ths_cycle
        from shared.config import load_config
        from shared.task_state import TaskStateStore

        # 中签归属最近申购业务日；与 catch-up 共用状态门，结果未变化不重复推送。
        store = TaskStateStore()
        day = allotment_business_day(store, date.today())
        result = run_ths_cycle(day, "allotment", cfg=load_config(), store=store, allow_recheck=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.cmd == "catch-up":
        from scheduler.catchup import catch_up, wait_network
        from shared.config import load_config

        cfg = load_config()
        boot_cfg = cfg.get("boot_login") or {}
        wait_network(boot_cfg.get("probe_url", "http://www.baidu.com"),
                     int(boot_cfg.get("network_timeout_s", 600)))

        result = catch_up(args.date or date.today().isoformat(), live=args.live)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if any(isinstance(item, dict) and item.get("status") in
               {"retryable", "blocked_uncertain", "manual_required", "lifecycle_failed"}
               for item in result.values()):
            raise SystemExit(1)
    elif args.cmd == "ths-cycle":
        from scheduler.catchup import run_ths_cycle
        from shared.config import load_config

        result = run_ths_cycle(args.date or date.today().isoformat(), args.phase,
                               live=args.live, cfg=load_config(), force_retry=args.force_retry)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if any(isinstance(item, dict) and item.get("status") in
               {"retryable", "blocked_uncertain", "manual_required", "lifecycle_failed"}
               for item in result.values()):
            raise SystemExit(1)
    elif args.cmd == "doctor":
        from shared.doctor import run_doctor

        result = run_doctor()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["ok"]:
            raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        from shared.errors import format_error, save_error_report

        path = save_error_report(exc, command=" ".join(sys.argv[1:]))
        print(format_error(exc), file=sys.stderr)
        print(f"错误详情: {path}", file=sys.stderr)
        raise SystemExit(1)
