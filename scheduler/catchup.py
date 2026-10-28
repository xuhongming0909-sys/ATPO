# AI-SUMMARY: 开机联网错过后补——日历/申购/中签幂等编排、生命周期包装和回执状态记录
from __future__ import annotations

import contextlib
import os
import threading
import time
from datetime import date as date_cls, datetime, time as time_cls, timedelta
from functools import wraps
from typing import Any, Callable
from uuid import uuid4

from shared.account_identity import account_identity, unique_account_items
from shared.errors import AutoIpoError
from shared.paths import ensure_runtime_dirs, runtime_path
from shared.task_state import TaskStateStore, result_signature, sanitize
from data_fetch.trading_days import is_trading_day

_LOCK_LOCAL = threading.local()


def _parse_day(day: str) -> date_cls:
    try:
        return date_cls.fromisoformat(day)
    except ValueError as exc:
        raise ValueError("date 必须是 YYYY-MM-DD") from exc


def _parse_clock(value: str) -> time_cls:
    try:
        return time_cls.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("catchup.subscribe_skip_after 必须是 HH:MM") from exc


@contextlib.contextmanager
def _task_chain_lock(operation: str, timeout_s: float = 1200.0):
    """Logon/Network/计划任务共用互斥锁：状态检查、GUI 执行、状态写入全程覆盖。"""
    depth = int(getattr(_LOCK_LOCAL, "depth", 0))
    if depth:
        _LOCK_LOCAL.depth = depth + 1
        try:
            yield
        finally:
            _LOCK_LOCAL.depth -= 1
        return

    ensure_runtime_dirs()
    lock_path = runtime_path("catchup.lock")
    marker = f"{os.getpid()}|{operation}|{datetime.now().isoformat(timespec='seconds')}|{uuid4().hex}"
    deadline = time.time() + timeout_s
    fd = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                from shared.gui_lock import _pid_active

                owner_pid = int(lock_path.read_text(encoding="utf-8").split("|", 1)[0])
                if not _pid_active(owner_pid):
                    lock_path.unlink()
                    continue
            except (OSError, ValueError):
                pass
            try:
                if time.time() - lock_path.stat().st_mtime > 2 * 60 * 60:
                    lock_path.unlink()
                    continue
            except OSError:
                pass
            if time.time() >= deadline:
                raise AutoIpoError(
                    "CATCHUP_LOCK_BUSY",
                    "另一个补任务正在执行",
                    "等待当前 catch-up/ths-cycle 结束后重试",
                    {"operation": operation},
                )
            time.sleep(0.25)
    _LOCK_LOCAL.depth = 1
    try:
        os.write(fd, marker.encode("utf-8"))
        os.close(fd)
        fd = None
        yield
    finally:
        _LOCK_LOCAL.depth = 0
        if fd is not None:
            os.close(fd)
        try:
            if lock_path.read_text(encoding="utf-8") == marker:
                lock_path.unlink()
        except OSError:
            pass


def _chain_locked(operation: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            with _task_chain_lock(operation):
                return fn(*args, **kwargs)
        return wrapper
    return decorator


def _default_send_receipt(kind: str, data: dict) -> str:
    try:
        from notification.receipts import send_receipt
    except Exception:
        return "unavailable"
    try:
        result = send_receipt(kind, data)
        if isinstance(result, dict) and result.get("sent") is False:
            return "skipped" if result.get("reason") == "disabled" else "failed"
        return "sent" if result is not None else "failed"
    except Exception:
        return "failed"


def _receipt_outcome(result: Any) -> str:
    """回执调用结果统一成状态字符串；失败不得误记 sent。"""
    if isinstance(result, dict):
        if result.get("sent") is False:
            return "skipped" if result.get("reason") == "disabled" else "failed"
        status = str(result.get("receipt_status") or "").lower()
        if status in {"sent", "skipped", "not_required", "failed", "unavailable"}:
            return status
        return "sent" if result.get("sent") else "failed"
    if isinstance(result, str):
        status = result.lower()
        return status if status in {"sent", "skipped", "not_required", "failed", "unavailable"} else "failed"
    return "sent" if result is not None else "failed"



def _receipt_enabled(cfg: dict, kind: str) -> bool:
    return bool(cfg.get("notification_receipts", {}).get(f"send_{kind}", True))


def _result_items(result: Any, account: str = "") -> list[dict]:
    """把执行结果递归摊平成带账户标签的明细行，供回执渲染与结果指纹。"""
    if isinstance(result, dict):
        label = str(result.get("account") or result.get("label") or account or "")
        nested = result.get("results") or result.get("items")
        if isinstance(nested, list):
            return _result_items(nested, label)
        if result.get("status") or result.get("apply_code"):
            row = dict(result)
            row.setdefault("account", label)
            return [row]
        clients = result.get("clients")
        if isinstance(clients, list):
            return _result_items(clients, label)
        return []
    if isinstance(result, list):
        items: list[dict] = []
        for row in result:
            items.extend(_result_items(row, account))
        return items
    return []


def _receipt_data(day: str, summary: str, result: Any, next_action: str = "") -> dict:
    if not isinstance(summary, dict):
        summary = {"note": str(summary)}
    if isinstance(result, dict):
        clients = result.get("clients", [])
    elif isinstance(result, list):
        clients = result
    else:
        clients = []
    items = _result_items(result)
    return sanitize({
        "date": day,
        "summary": summary,
        "clients": clients,
        "items": items,
        "next_action": next_action,
    })



def wait_network(probe_url: str = "http://www.baidu.com", timeout_s: int = 600) -> None:
    """等网络就绪：收到任意 HTTP 应答（含 4xx/5xx）即算联网；超时放弃本次。"""
    import time
    import urllib.error
    from urllib.request import urlopen

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            urlopen(probe_url, timeout=10)
            return
        except urllib.error.HTTPError:
            return
        except Exception:
            time.sleep(5)


@_chain_locked("catch-up")
def catch_up(
    day: str,
    *,
    live: bool = False,
    now: datetime | None = None,
    cfg: dict | None = None,
    store: TaskStateStore | None = None,
    daily_report: Callable[..., Any] | None = None,
    send_receipt: Callable[[str, dict], str] | None = None,
) -> dict[str, dict]:
    """补当日错过的日历推送、窗口内申购和未定中签查询。已完成且已推送不重复；非交易日整体跳过。"""
    if cfg is None:
        from shared.config import load_config
        cfg = load_config()
    if not cfg.get("catchup", {}).get("enabled", True):
        return {"catchup": {"status": "disabled", "receipt_status": "not_required"}}
    if is_trading_day(day) is False:
        return {"status": "skipped_non_trading", "date": day, "receipt_status": "not_required"}
    business_day = _parse_day(day)
    current = now or datetime.now()
    states = store or TaskStateStore()
    receipt = send_receipt or _default_send_receipt
    output: dict[str, dict] = {}

    # 日历推送：推送成功或明确跳过空日历后才算完成。
    previous = states.get("daily_report", day, "live")
    if previous and previous.status == "completed" and previous.receipt_status in {"sent", "not_required", "skipped"}:
        output["daily_report"] = {"status": "skipped_completed", "receipt_status": previous.receipt_status}
    else:
        try:
            call = daily_report or (lambda **kw: __import__("scheduler.jobs", fromlist=["daily_report"]).daily_report(**kw))
            messages = call(day=day, push=True)
            receipt_status = "sent" if messages else "not_required"
            states.record("daily_report", day, "completed", receipt_status=receipt_status, mode="live",
                          payload={"message_count": len(messages or [])})
            output["daily_report"] = {"status": "completed", "receipt_status": receipt_status}
        except Exception as exc:
            states.record("daily_report", day, "retryable", receipt_status="failed", mode="live", error=exc)
            output["daily_report"] = {"status": "retryable", "error": str(exc)[:200]}

    # 登录/申购/中签统一走 ths-cycle 幂等门；中签再扫保留期内其他申购业务日。
    primary_allotment_day = allotment_business_day(states, business_day)
    output.update(run_ths_cycle(day, "all", live=live, cfg=cfg, store=states,
                                receipt=receipt, now=current,
                                allotment_day=primary_allotment_day))
    keep_days = int(cfg.get("catchup", {}).get("allotment_keep_days", 3))
    for bday in _allotment_business_days(states, day, keep_days):
        if bday == primary_allotment_day:
            continue
        swept = run_ths_cycle(bday, "allotment", live=live, cfg=cfg, store=states,
                              receipt=receipt, now=current, allotment_day=bday)
        key = "allotment" if bday == day else f"allotment:{bday}"
        output[key] = swept.get("allotment", {"status": "missing"})
        if "lifecycle" in swept:
            output[f"lifecycle:{bday}"] = swept["lifecycle"]
    return output


def allotment_business_day(store: TaskStateStore, today: date_cls) -> str:
    """中签查询归属最近一次申购业务日；无申购记录时按当天。"""
    days = [t.date for t in store.list() if t.task == "subscribe" and t.date <= today.isoformat()]
    return max(days) if days else today.isoformat()


def _allotment_business_days(store: TaskStateStore, day: str, keep_days: int) -> list[str]:
    """只按保留期内真实申购业务日补查；无申购记录时才回退目标日。"""
    start = (_parse_day(day) - timedelta(days=keep_days)).isoformat()
    days = {t.date for t in store.list() if t.task == "subscribe" and start <= t.date <= day}
    return sorted(days or {day})


def _allotment_published(cfg: dict, business_day: date_cls, current: datetime, items: list[dict]) -> bool:
    """数据真正公布才算最终结果：有结构化明细，或过 T+1 预定查询时点。"""
    rows = [i for i in items if str(i.get("status", "")).lower() not in
            {"failed", "unpublished", "not_published", "data_unavailable", "pending"}]
    if rows:
        return True
    clock = _parse_clock(str(cfg.get("schedule", {}).get("allotment_check_1", "22:00")))
    return (current.date(), current.time()) >= (business_day + timedelta(days=1), clock)


THS_PHASES = ("login", "subscribe", "allotment")
_TERMINAL_RECEIPTS = {"sent", "not_required", "skipped"}
_LIFECYCLE_IMAGES = {"hexin.exe", "xiadan.exe", "xiadan-plus.exe"}


def _ths_phases(phase: str) -> list[str]:
    if phase == "all":
        return list(THS_PHASES)
    if phase in THS_PHASES:
        return [phase]
    raise ValueError("phase 仅支持 login/subscribe/allotment/all")


def _ths_task_mode(phase: str, live: bool) -> str:
    """登录/中签只读且始终使用 live 状态键；只有申购区分 dry_run/live。"""
    return "dry_run" if phase == "subscribe" and not live else "live"


def _default_lifecycle_probe() -> dict:
    """只读检查任务后 hexin/xiadan/xiadan-plus 残留；绝不尝试关闭或强杀。"""
    import csv
    import subprocess

    try:
        proc = subprocess.run(
            ["tasklist.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10, check=False,
        )
    except Exception as exc:
        return {"status": "probe_failed", "error": str(exc)[:200], "residual_processes": []}
    if proc.returncode != 0:
        return {"status": "probe_failed", "error": f"tasklist exit={proc.returncode}",
                "residual_processes": []}
    counts: dict[str, int] = {}
    for row in csv.reader(proc.stdout.splitlines()):
        if not row:
            continue
        name = row[0].strip().lower()
        if name in _LIFECYCLE_IMAGES:
            counts[name] = counts.get(name, 0) + 1
    residual = [{"image_name": name, "count": counts[name]} for name in sorted(counts)]
    return {"status": "clean" if not residual else "residual", "residual_processes": residual}


def _lifecycle_assessment(workflow_results: list[dict], probe: dict) -> dict:
    close_errors = [row for result in workflow_results for row in (result.get("close_errors") or [])]
    close_states = [result.get("lifecycle_close") or {} for result in workflow_results]
    close_ok = bool(close_states) and not close_errors and all(
        isinstance(state, dict) and state.get("status") == "closed" for state in close_states
    )
    residual = probe.get("residual_processes") or []
    probe_ok = probe.get("status") == "clean" and not residual
    status = "completed" if close_ok and probe_ok else "lifecycle_failed"
    return sanitize({
        "status": status,
        "close_status": "closed" if close_ok else "close_failed",
        "residual_processes": residual,
        "errors": close_errors or ([] if probe_ok else [probe.get("error") or "任务后仍有客户端进程残留"]),
    })


def _retry_receipt_from_state(
    phase: str,
    previous,
    *,
    cfg: dict,
    states: TaskStateStore,
    day: str,
    mode: str,
    receipt_fn: Callable[[str, dict], Any],
    output: dict[str, dict],
) -> bool:
    """已有结果但回执缺失时只补发，不重新启动客户端或重放申购。"""
    payload = previous.payload if isinstance(previous.payload, dict) else {}
    data = payload.get("receipt_data")
    if not isinstance(data, dict):
        return False
    if not _receipt_enabled(cfg, phase):
        receipt_status = "skipped"
    else:
        try:
            receipt_status = _receipt_outcome(receipt_fn(phase, dict(data)))
        except Exception:
            receipt_status = "failed"
    states.record(phase, day, previous.status, receipt_status=receipt_status, mode=mode,
                  payload=previous.payload, completed_at=previous.completed_at,
                  error=previous.sanitized_error)
    output[phase] = {"status": "receipt_retried", "receipt_status": receipt_status}
    return True


def _ths_phase_items(rows: list[dict], phase: str) -> list[dict]:
    """把 ths_account_runner 账户行按阶段摊平成回执/去重用结构化明细。"""
    items: list[dict] = []
    for row in rows:
        ths_username = str(row.get("username") or row.get("display_name") or row.get("account") or "")
        if phase == "login":
            fund_rows = [item for item in (row.get("fund_accounts") or []) if isinstance(item, dict)]
            for fund_row in fund_rows:
                identity = account_identity(ths_username, fund_row)
                login_status = str(fund_row.get("login_status") or fund_row.get("status") or "failed")
                items.append({
                    **identity,
                    "status": login_status,
                    "login_status": login_status,
                    "dialog_required": bool(fund_row.get("dialog_required")),
                    "manual_required": bool(fund_row.get("manual_required")),
                    "detail": fund_row.get("error") or fund_row.get("detail") or "",
                    "error_code": fund_row.get("error_code", ""),
                })
            if not fund_rows and str(row.get("status", "")) != "completed":
                identity = account_identity(ths_username, row)
                status = str(row.get("status") or "failed")
                items.append({
                    **identity,
                    "status": status,
                    "login_status": status,
                    "dialog_required": False,
                    "manual_required": status == "manual_required",
                    "detail": row.get("error") or "",
                    "error_code": row.get("error_code", ""),
                })
            continue
        task_rows = row.get(phase) or []
        for task_row in task_rows if isinstance(task_rows, list) else [task_rows]:
            if not isinstance(task_row, dict):
                continue
            if phase == "allotment" and not (
                task_row.get("证券代码") or task_row.get("apply_code")
                or task_row.get("证券名称") or task_row.get("name")
            ):
                continue  # 无标的身份的行不算中签（防网格误读产生幻影中签）
            identity = account_identity(ths_username, task_row)
            item = {**identity}
            if phase == "subscribe":
                item.update({"name": task_row.get("name"),
                             "apply_code": task_row.get("apply_code"),
                             "amount": task_row.get("amount"), "unit": task_row.get("unit"),
                             "status": task_row.get("status"), "reason": task_row.get("reason")})
            else:
                item.update({"name": task_row.get("证券名称") or task_row.get("name"),
                             "apply_code": task_row.get("证券代码") or task_row.get("apply_code"),
                             "winning_qty": task_row.get("中签数量") or task_row.get("winning_qty"),
                             "payment_amount": task_row.get("缴款金额") or task_row.get("payment_amount"),
                             "status": task_row.get("status") or "won"})
            items.append(item)
    return unique_account_items(items) if phase == "login" else items


def _ths_phase_status(phase: str, items: list[dict], result: dict, current: datetime,
                      business_day: date_cls, cfg: dict) -> tuple[str, str]:
    if phase == "subscribe":
        states_seen = [str(i.get("status", "")).lower() for i in items]
        workflow_status = str(result.get("status") or "").lower()
        if not items and workflow_status in {"failed", "partial"}:
            return "retryable", "GUI 工作流失败，未产生可核验申购明细"
        if any(s in {"unknown", "submitted_unverified"} for s in states_seen):
            return "blocked_uncertain", "存在不确定委托状态，禁止自动重试"
        if any(s in {"failed", "failed_confirmed"} for s in states_seen):
            return "retryable", "部分申购失败"
        return "completed", ""
    if phase == "allotment":
        published = _allotment_published(cfg, business_day, current, items)
        return ("completed" if published else "retryable",
                "" if published else "数据未公布，不算最终无中签，将继续补查")
    if any(bool(item.get("manual_required")) or str(item.get("status", "")) == "manual_required"
           for item in items):
        return "manual_required", "出现其他安全验证/人工弹窗，已停止后续账户"
    failed = [
        item for item in items
        if str(item.get("login_status") or item.get("status", "")).lower() not in
        {"ready", "already_logged_in", "success", "logged_in"}
    ]
    return ("retryable" if failed or result.get("error_code") else "completed",
            "存在登录失败账户" if failed else str(result.get("error") or ""))


@_chain_locked("ths-cycle")
def run_ths_cycle(day: str, phase: str = "all", *, live: bool = False, force_retry: bool = False,
                  cfg: dict | None = None, store: TaskStateStore | None = None,
                  receipt: Callable[[str, dict], Any] | None = None,
                  workflow: Callable[..., dict] | None = None,
                  now: datetime | None = None, allow_recheck: bool = False,
                  process_probe: Callable[[], dict] | None = None,
                  allotment_day: str | None = None) -> dict:
    """ths_account_switch 模式统一入口：按业务日补缺，过期申购不回放，任务后验收无残留。"""
    if cfg is None:
        from shared.config import load_config
        cfg = load_config()
    states = store or TaskStateStore()
    current = now or datetime.now()
    receipt_fn = receipt or _default_send_receipt
    business_day = _parse_day(day)
    allotment_business_date = (
        _parse_day(allotment_day) if allotment_day
        else _parse_day(allotment_business_day(states, business_day))
    )
    cutoff = _parse_clock(str(cfg.get("catchup", {}).get("subscribe_skip_after", "15:00")))
    out: dict[str, dict] = {}
    pending: list[tuple[str, str]] = []

    for ph in _ths_phases(phase):
        # 非交易日不启动：登录/申购看业务日，中签看运行日
        gate_day = current.date().isoformat() if ph == "allotment" else day
        if is_trading_day(gate_day) is False:
            out[ph] = {"status": "skipped_non_trading", "receipt_status": "not_required",
                       "business_day": gate_day}
            continue
        target_day = allotment_business_date.isoformat() if ph == "allotment" else day
        task_mode = _ths_task_mode(ph, live)
        previous = None if force_retry and ph == "subscribe" else states.get(ph, target_day, task_mode)
        if previous and previous.status == "blocked_uncertain":
            if previous.receipt_status not in _TERMINAL_RECEIPTS and _retry_receipt_from_state(
                ph, previous, cfg=cfg, states=states, day=target_day, mode=task_mode,
                receipt_fn=receipt_fn, output=out,
            ):
                continue
            out[ph] = {"status": "blocked_uncertain", "receipt_status": previous.receipt_status}
            continue
        if (ph == "subscribe" or (phase == "all" and ph == "login")) and current.date() == business_day:
            window = (cfg.get("schedule") or {}).get("subscribe_window") or ["09:30", "15:00"]
            try:
                window_start = _parse_clock(str(window[0]))
            except Exception:
                window_start = _parse_clock("09:30")
            if current.time() < window_start:
                out[ph] = {"status": "pending_window", "receipt_status": "not_required"}
                continue
        if ph == "subscribe" and (current.date() > business_day or
                                  (current.date() == business_day and current.time() > cutoff)):
            states.record("subscribe", day, "skipped_expired", receipt_status="not_required",
                          mode=task_mode, completed_at=current.isoformat(timespec="seconds"),
                          error=f"已过申购补做时间 {cutoff.strftime('%H:%M')}")
            out["subscribe"] = {"status": "skipped_expired", "receipt_status": "not_required"}
            continue
        if previous and previous.status == "skipped_expired":
            out[ph] = {"status": "skipped_expired", "receipt_status": previous.receipt_status}
            continue
        if previous and previous.status == "completed":
            receipt_ok = previous.receipt_status in _TERMINAL_RECEIPTS
            if not receipt_ok and _retry_receipt_from_state(
                ph, previous, cfg=cfg, states=states, day=target_day, mode=task_mode,
                receipt_fn=receipt_fn, output=out,
            ):
                continue
            if receipt_ok and not (ph == "allotment" and allow_recheck):
                out[ph] = {"status": "skipped_completed", "receipt_status": previous.receipt_status}
                continue
            if ph == "subscribe" and not receipt_ok:
                out[ph] = {
                    "status": "blocked_uncertain",
                    "receipt_status": previous.receipt_status,
                    "reason": "申购结果缺少可补发回执负载，禁止重新下单",
                }
                continue
        pending.append((ph, target_day))

    if not pending:
        return out

    run_workflow = workflow or (
        lambda **kw: __import__("execution.ths_account_runner",
                                fromlist=["run_ths_account_workflow"]).run_ths_account_workflow(cfg, **kw))
    if process_probe is not None:
        probe_fn = process_probe
    elif workflow is not None:
        probe_fn = lambda: {"status": "clean", "residual_processes": []}
    else:
        probe_fn = _default_lifecycle_probe
    receipt_suppressor = lambda kind, payload: {"kind": kind, "sent": True, "payload": dict(payload)}
    workflow_results: list[dict] = []

    for ph, target_day in pending:
        try:
            result = run_workflow(day=target_day, live=live, phase=ph,
                                  force_retry=force_retry, receipt_sender=receipt_suppressor)
            workflow_results.append(result)
        except Exception as exc:
            task_mode = _ths_task_mode(ph, live)
            states.record(ph, target_day, "retryable", receipt_status="failed", mode=task_mode,
                          completed_at=current.isoformat(timespec="seconds"), error=exc)
            out[ph] = {"status": "retryable", "error": str(exc)[:200]}
            continue

        task_mode = _ths_task_mode(ph, live)
        account_rows = [r for r in (result.get("ths_accounts") or []) if isinstance(r, dict)]
        items = _ths_phase_items(account_rows, ph)
        status, error = _ths_phase_status(ph, items, result, current,
                                          _parse_day(target_day), cfg)
        previous = states.get(ph, target_day, task_mode)
        prev_payload = previous.payload if previous and isinstance(previous.payload, dict) else {}
        signature = result_signature({"items": items, "status": status})
        if ph == "login":
            data = sanitize({
                "date": target_day,
                "summary": {},
                "clients": [{"client_id": "ths_account_switch", "accounts": items}],
                "items": items,
                "next_action": error or "",
            })
        else:
            data = _receipt_data(target_day, {"phase": ph, "status": status}, items,
                                 error or ("中签当日 16:00 前备足缴款资金。" if ph == "allotment"
                                           else "失败或不确定项人工核对当日委托，禁止重复提交。"))
        same_result = prev_payload.get("result_signature") == signature
        receipt_ok = bool(previous and previous.receipt_status in _TERMINAL_RECEIPTS)
        should_push = not (ph in {"login", "allotment"} and same_result and receipt_ok)
        # 2026-10-27：Server酱免费版日限 5 条；"数据未公布"的中间态不推送（烧额度且无结论），
        # 只推最终结果（中签/最终无中签）。T1/T2 多次补查不再每次发消息。
        if ph == "allotment" and status == "retryable" and "数据未公布" in (error or ""):
            should_push = False
        receipt_status = previous.receipt_status if previous and not should_push else "not_sent"
        if should_push:
            try:
                receipt_status = _receipt_outcome(receipt_fn(ph, data))
            except Exception:
                receipt_status = "failed"
        payload = {"items": items, "result_signature": signature, "receipt_data": data}
        states.record(ph, target_day, status, receipt_status=receipt_status, mode=task_mode,
                      completed_at=current.isoformat(timespec="seconds"),
                      payload=payload, error=error)
        phase_out = {"status": status, "receipt_status": receipt_status,
                     "business_day": target_day, "items": sanitize(items)}
        if not should_push:
            phase_out["dedup_unchanged"] = True
        out[ph] = phase_out

    try:
        probe = probe_fn()
    except Exception as exc:
        probe = {"status": "probe_failed", "error": str(exc)[:200], "residual_processes": []}
    lifecycle = _lifecycle_assessment(workflow_results, probe)
    states.record("lifecycle", day, lifecycle["status"], receipt_status="not_required",
                  mode="live", completed_at=current.isoformat(timespec="seconds"),
                  payload=lifecycle, error="; ".join(str(x) for x in lifecycle.get("errors", [])))
    out["lifecycle"] = lifecycle
    return out

