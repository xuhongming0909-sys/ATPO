# AI-SUMMARY: 单同花顺多登录账户编排——全局 GUI 锁、串行切户、逐资金账户任务、温和退出和即时落盘
from __future__ import annotations
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any

from execution.client_registry import ClientSpec
from execution.ths_account_config import load_ths_account_mode, read_ths_password
from execution.ths_account_switch import MAX_THS_LOGIN_ACCOUNTS, ThsLoginAccount, close_ths_client, switch_ths_account
from shared.errors import AutoIpoError, sanitize_sensitive_text, sanitize_sensitive_value
from shared.account_identity import account_identity, unique_account_items
from shared.gui_lock import gui_lock


_HASH_KEYS = {"fund_account_hash", "target_key", "key"}
_HEX_HASH = __import__("re").compile(r"^[0-9a-f]{16,64}$", __import__("re").I)


@dataclass
class ThsAccountTaskContext:
    day: str
    live: bool
    mode: str
    ths_username: str
    fund_account: dict[str, Any]
    client: ClientSpec
    cfg: dict[str, Any]
    phase: str = "all"
    force_retry: bool = False


class GentleClientLifecycle:
    """只启动 hexin；任务后核验并温和关闭 hexin/xiadan/xiadan-plus。"""

    def __init__(self, client: ClientSpec, cfg: Mapping[str, Any]):
        self.client = client
        self.cfg = dict(cfg or {})
        self.hexin_pids: list[int] = []
        self.xiadan_pids: list[int] = []
        self.preexisting = False
        self._baseline: dict[str, set[int]] = {}
        self._tracked: dict[str, set[int]] = {}

    def start(self) -> None:
        from execution.client_lifecycle import _start, find_processes

        paths = self._process_paths()
        found = find_processes(paths)
        self._baseline = {str(path): set(found.get(str(path), [])) for path in paths}
        self._tracked = {str(path): set(pids) for path, pids in self._baseline.items()}
        self.hexin_pids = sorted(self._baseline[str(self.client.hexin_path)])
        self.xiadan_pids = sorted(self._baseline[str(self.client.xiadan_path)])
        self.preexisting = bool(self.hexin_pids)
        if not self.hexin_pids:
            pid = _start(self.client.hexin_path, set())
            if not pid:
                raise AutoIpoError(
                    "CLIENT_START_PID_MISSING",
                    "同花顺主程序启动后未取得 PID",
                    "检查 execution.ths_account_switch.hexin_path",
                    {"hexin_path": str(self.client.hexin_path)},
                )
            self.hexin_pids = [pid]
            self._tracked[str(self.client.hexin_path)].add(pid)

    def _process_paths(self) -> list[Path]:
        return [
            self.client.hexin_path,
            self.client.xiadan_path,
            Path(self.client.xiadan_path).parent / "xiadan-plus" / "xiadan-plus.exe",
        ]

    def _origin(self, path: Path, pid: int) -> str:
        return "preexisting" if pid in self._baseline.get(str(path), set()) else "task_started"

    def _merge_found(self, paths: list[Path], found: Mapping[str, list[int]]) -> dict[str, set[int]]:
        merged: dict[str, set[int]] = {}
        for path in paths:
            key = str(path)
            pids = set(found.get(key, []))
            merged[key] = pids
            self._tracked.setdefault(key, set()).update(pids)
        return merged

    def _close_failed(self, errors: list[str]) -> dict[str, Any]:
        return {
            "status": "close_failed",
            "error_code": "CLIENT_CLOSE_FAILED",
            "error": "; ".join(errors) or "任务后客户端进程残留",
            "closed_pids": [],
            "preexisting_pids": sorted({pid for pids in self._baseline.values() for pid in pids}),
            "task_started_pids": [],
            "processes": [],
            "residual_processes": [],
            "errors": errors,
        }

    def close(self) -> dict[str, Any]:
        from execution.client_lifecycle import _close_pid, find_processes

        settings = (self.cfg.get("gui") or {}).get("lifecycle") or {}
        timeout_s = float(settings.get("close_timeout_s", 15))
        close_after = bool(settings.get("close_after_task", True))
        close_preexisting = bool(settings.get("close_preexisting", True))
        paths = self._process_paths()
        from execution.client_lifecycle import confirm_exit_dialogs as _confirm_exit_dialogs

        closer = lambda pid, timeout: _close_pid(pid, timeout, _on_wait=lambda: _confirm_exit_dialogs(dialog_pids))
        errors: list[str] = []
        closed: list[int] = []
        process_rows: list[dict[str, Any]] = []

        try:
            current = self._merge_found(paths, find_processes(paths))
        except Exception as exc:
            return self._close_failed([f"残余进程核验失败：{str(exc)[:150]}"])
        if not any(current.values()):
            # 2026-10-24 实战：tasklist 瞬断会把"没扫到"误报成 closed；已知有跟踪进程仍活跃时必须 fail
            from execution.client_lifecycle import _pid_active
            tracked_active = any(
                _pid_active(pid) for pids in self._tracked.values() for pid in pids
            )
            if tracked_active:
                time.sleep(2.0)
                current = self._merge_found(paths, find_processes(paths))
            if not any(current.values()) and tracked_active:
                return self._close_failed(["残余进程核验异常：扫描为空但已跟踪进程仍活跃"])
        dialog_pids = {int(pid) for pids in current.values() for pid in pids}

        def safe_close(pid: int) -> tuple[bool, str]:
            try:
                return closer(pid, timeout_s)
            except Exception as exc:
                return False, _safe(f"温和关闭异常：{type(exc).__name__}")

        def should_close_pid(path: Path, pid: int) -> bool:
            origin = self._origin(path, pid)
            return close_after and (origin == "task_started" or close_preexisting)

        for path in reversed(paths):
            for pid in sorted(current[str(path)]):
                origin = self._origin(path, pid)
                should_close = should_close_pid(path, pid)
                row = {
                    "image_name": path.name,
                    "path": str(path),
                    "pid": pid,
                    "origin": origin,
                    "close_status": "pending" if should_close else "kept_by_config",
                    "error": "",
                }
                process_rows.append(row)
                if not should_close:
                    continue
                ok, error = safe_close(pid)
                row["close_status"] = "closed" if ok else "failed"
                row["error"] = "" if ok else error
                if ok:
                    closed.append(pid)
                else:
                    errors.append(_safe(error))

        try:
            second = self._merge_found(paths, find_processes(paths))
            for path in reversed(paths):
                for pid in sorted(second[str(path)] - current[str(path)]):
                    origin = self._origin(path, pid)
                    if not should_close_pid(path, pid):
                        process_rows.append({
                            "image_name": path.name,
                            "path": str(path),
                            "pid": pid,
                            "origin": origin,
                            "close_status": "kept_by_config",
                            "error": "",
                        })
                        continue
                    ok, error = safe_close(pid)
                    process_rows.append({
                        "image_name": path.name,
                        "path": str(path),
                        "pid": pid,
                        "origin": origin,
                        "close_status": "closed" if ok else "failed",
                        "error": "" if ok else error,
                    })
                    if ok:
                        closed.append(pid)
                    else:
                        errors.append(_safe(error))
            residual_found = self._merge_found(paths, find_processes(paths))
        except Exception as exc:
            return self._close_failed(errors + [f"残余进程核验失败：{str(exc)[:150]}"])

        residual_processes = []
        for path in reversed(paths):
            pids = sorted(pid for pid in residual_found[str(path)] if should_close_pid(path, pid))
            if not pids:
                continue
            origins = {self._origin(path, pid) for pid in pids}
            residual_processes.append({
                "image_name": path.name,
                "path": str(path),
                "pids": pids,
                "count": len(pids),
                "origin": origins.pop() if len(origins) == 1 else "mixed",
                "error_code": "CLIENT_CLOSE_FAILED",
            })

        baseline_pids = sorted({pid for pids in self._baseline.values() for pid in pids})
        task_started = sorted({
            pid
            for path, pids in self._tracked.items()
            for pid in pids
            if self._origin(Path(path), pid) == "task_started"
        })
        failed_rows = [row for row in process_rows if row.get("close_status") == "failed"]
        kept_rows = [row for row in process_rows if row.get("close_status") == "kept_by_config"]
        if residual_processes:
            errors.append("任务后仍有 hexin/xiadan/xiadan-plus 进程残留")
        failed = bool(residual_processes or failed_rows)
        status = "close_failed" if failed else "kept_by_config" if kept_rows else "closed"
        return {
            "status": status,
            "error_code": "CLIENT_CLOSE_FAILED" if failed else "",
            "error": "; ".join(errors) if failed else "",
            "closed_pids": sorted(set(closed)),
            "preexisting_pids": baseline_pids,
            "task_started_pids": task_started,
            "processes": process_rows,
            "residual_processes": residual_processes,
            "errors": errors,
        }


def _safe(value: object) -> str:
    return sanitize_sensitive_text(value)


_ACCOUNT_ID_KEYS = {"fund_account", "fund_account_tail4"}


def _safe_value(value: Any, key: str = "") -> Any:
    if key in _HASH_KEYS and isinstance(value, str) and _HEX_HASH.fullmatch(value):
        return value
    if key.lower() in _ACCOUNT_ID_KEYS and isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return {str(name): _safe_value(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_value(item) for item in value]
    return sanitize_sensitive_value(value)


def _error_row(exc: Exception, status: str = "failed") -> dict[str, Any]:
    code = exc.code if isinstance(exc, AutoIpoError) else "UNEXPECTED_ERROR"
    return {
        "status": status,
        "error_code": _safe(code),
        "error": _safe(exc),
    }


def _result_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    elif is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    raw = dict(value or {})
    clean = _safe_value(raw)
    return dict(clean)


def _fund_identity(row: Mapping[str, Any], ref: Any) -> dict[str, Any]:
    safe = ref.safe_dict() if hasattr(ref, "safe_dict") else _safe_value(dict(ref or {}))
    safe.update({
        key: value
        for key, value in dict(row or {}).items()
        if key in {
            "status",
            "dialog_required",
            "manual_required",
            "xiadan_present",
            "error_code",
            "error",
        }
    })
    return _safe_value(safe)


def default_result_writer(day: str) -> Callable[[Mapping[str, Any]], None]:
    from shared.paths import ensure_runtime_dirs, runtime_path

    def write(snapshot: Mapping[str, Any]) -> None:
        import json

        ensure_runtime_dirs()
        path = runtime_path("ths_accounts", f"{day}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(path.name + ".tmp")
        try:
            tmp_path.write_text(
                json.dumps(_safe_value(dict(snapshot)), ensure_ascii=False, indent=2),
                encoding="utf-8",
                newline="\n",
            )
            tmp_path.replace(path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    return write


def default_receipt_sender(kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    from notification.receipts import send_receipt

    return send_receipt(kind, dict(payload))


def _blocked_codes(blacklist: Any) -> set[str]:
    values = blacklist if isinstance(blacklist, (list, tuple, set)) else [blacklist]
    blocked: set[str] = set()
    for item in values:
        if isinstance(item, Mapping):
            for key in ("code", "apply_code"):
                value = item.get(key)
                if value is not None:
                    blocked.add(str(value).replace(" ", ""))
        elif item is not None:
            blocked.add(str(item).replace(" ", ""))
    return blocked


def _subscribe_status(rows: list[Mapping[str, Any]]) -> str:
    states = {str(row.get("status", "")).lower() for row in rows}
    if states & {"failed", "failed_confirmed", "batch_rejected", "rejected"}:
        return "failed"
    if states & {"unknown", "submitted_unverified", "partial"}:
        return "partial"
    return "completed"


def _allotment_row_belongs(row: Mapping[str, Any], day: str, apply_codes: set[str]) -> bool:
    """中签明细页含全部历史，严格过滤：只认本业务日及以后、且属于本业务日申购标的的行。

    日期缺失的行仅在证券代码匹配本业务日申购标的时保留（2026-10-24 修复：
    缺失日期一律保留曾把许*鸣融 5 条历史中签误当当日结果，提前 completed 挡住后续补查）。
    """
    raw = str(row.get("中签日期") or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) >= 8:
        return int(digits[:8]) >= int(day.replace("-", "")) and _row_code_in(row, apply_codes)
    return _row_code_in(row, apply_codes)


def _row_code_in(row: Mapping[str, Any], apply_codes: set[str]) -> bool:
    code = str(row.get("apply_code") or row.get("证券代码") or "").replace(" ", "").strip()
    return bool(code) and code in apply_codes


def default_account_task(ctx: ThsAccountTaskContext) -> dict[str, Any]:
    """按 phase 执行申购/中签；all 保留申购→F8→中签全链路。"""
    if ctx.phase == "login":
        return {"status": "completed"}
    if ctx.phase == "subscribe" and ctx.mode == "skipped_expired":
        return {
            "status": "skipped_expired",
            "subscribe": [{"status": "skipped", "reason": "申购时段已过，不执行申购"}],
        }

    from data_fetch.calendar import fetch_calendar_for
    from execution.allotment import query_allotment
    from execution.login import close_modal_dialogs
    from execution.ipo_page import batch_subscribe
    from execution.order_ledger import OrderLedger
    from execution.subscribe import calendar_allowlist, execute, uncovered_orders
    from execution.ths_client import connect

    blacklist = ctx.cfg.get("strategy", {}).get("blacklist", [])
    blocked = _blocked_codes(blacklist)
    subscribe_rows: list[dict[str, Any]] = []
    allotment_rows: list[dict[str, Any]] = []
    stage_durations: dict[str, float] = {}
    entrust_error = ""
    allotment_error = ""

    run_subscribe = ctx.phase in {"subscribe", "all"} and ctx.mode != "skipped_expired"
    if run_subscribe:
        stage_t0 = time.monotonic()
        calendar = fetch_calendar_for(ctx.day)
        stage_durations["calendar_s"] = round(time.monotonic() - stage_t0, 3)
        raw_orders = calendar_allowlist(calendar, [])
        # 2026-10-28 用户拍板：北交所（920/43/83/87/88 开头）无需申购，默认排除并留痕
        from execution.subscribe import _is_bse_code
        bse_orders = [o for o in raw_orders if _is_bse_code(o.get("apply_code") or o.get("code"))]
        orders = [
            order for order in raw_orders
            if not _is_bse_code(order.get("apply_code") or order.get("code"))
            and str(order.get("code", "")).replace(" ", "") not in blocked
            and str(order.get("apply_code", "")).replace(" ", "") not in blocked
        ]
        stage_t0 = time.monotonic()
        user = connect(client=ctx.client)
        stage_durations["connect_s"] = round(time.monotonic() - stage_t0, 3)
        # 2026-10-27：上一户不确定状态可能残留模态弹窗（如委托确认框），会卡死本户批量页导航。
        # 任务前先清一次，避免级联卡死（此前只在该户任务结束才清，挡不住户间传染）。
        try:
            close_modal_dialogs(client=ctx.client)
        except Exception:
            pass
        account_id = str(ctx.fund_account.get("target_key") or "")
        account_key = str(ctx.fund_account.get("fund_account_hash") or account_id)
        ledger = OrderLedger(ctx.day, allow_repeat=ctx.force_retry) if ctx.mode == "live" else None
        subscribe_rows = [
            {**o, "status": "skipped", "reason": "北交所标的无需申购（2026-10-28 用户拍板）",
             "error_code": "BSE_SKIPPED_BY_CONFIG", "verified": None}
            for o in bse_orders
        ]
        if ctx.mode == "live":
            stage_t0 = time.monotonic()
            subscribe_rows += batch_subscribe(
                user,
                ledger=ledger,
                account_id=account_id,
                account_key=account_key,
                client_id=ctx.ths_username,
                allowlist=orders,
                blacklist=blacklist,
            )
            stage_durations["subscribe_s"] = round(time.monotonic() - stage_t0, 3)
            rest = uncovered_orders(orders, subscribe_rows)
            if rest:
                subscribe_rows.extend(execute(
                    user,
                    rest,
                    "live",
                    ledger=ledger,
                    account_id=account_id,
                    account_key=account_key,
                    client_id=ctx.ths_username,
                    client=ctx.client,
                ))
        else:
            subscribe_rows += batch_subscribe(
                user,
                account_id=account_id,
                account_key=account_key,
                client_id=ctx.ths_username,
                allowlist=orders,
                blacklist=blacklist,
                dry_run=True,
            )
    else:
        stage_t0 = time.monotonic()
        user = connect(client=ctx.client)
        stage_durations["connect_s"] = round(time.monotonic() - stage_t0, 3)

    if ctx.phase in {"subscribe", "all"}:
        stage_t0 = time.monotonic()
        try:
            from execution.ths_client import read_today_entrusts_via_ocr
            today_entrusts = read_today_entrusts_via_ocr(user)
            if today_entrusts is None:
                raise RuntimeError("F8 \u5f53\u65e5\u59d4\u6258 OCR \u8bfb\u53d6\u5931\u8d25")
        except Exception as exc:
            today_entrusts = []
            entrust_error = _safe(exc)
        else:
            entrust_error = ""
        stage_durations["entrusts_s"] = round(time.monotonic() - stage_t0, 3)
    else:
        today_entrusts = []

    if ctx.phase in {"allotment", "all"}:
        stage_t0 = time.monotonic()
        try:
            day_calendar = fetch_calendar_for(ctx.day)
            day_codes = {
                str(item.get("apply_code") or item.get("code") or "").replace(" ", "").strip()
                for item in calendar_allowlist(day_calendar, [])
            } - {""}
            allotment_rows = [
                r for r in query_allotment(user)
                if _allotment_row_belongs(r, ctx.day, day_codes)
            ]
        except Exception as exc:
            allotment_rows = []
            allotment_error = _safe(exc)
        else:
            allotment_error = ""
        stage_durations["allotment_s"] = round(time.monotonic() - stage_t0, 3)

    close_modal_dialogs(client=ctx.client)

    subscribe_state = _subscribe_status(subscribe_rows) if ctx.phase in {"subscribe", "all"} else "completed"
    allotment_state = _subscribe_status(allotment_rows) if ctx.phase in {"allotment", "all"} else "completed"
    if ctx.phase == "allotment":
        status = allotment_state
        if allotment_error and status == "completed":
            status = "partial"
    elif ctx.phase == "subscribe":
        status = subscribe_state
        if entrust_error and status == "completed":
            status = "partial"
    else:
        if "failed" in {subscribe_state, allotment_state}:
            status = "failed"
        elif "partial" in {subscribe_state, allotment_state} or entrust_error or allotment_error:
            status = "partial"
        else:
            status = "completed"

    result: dict[str, Any] = {"status": status, "stage_durations_s": stage_durations}
    if ctx.phase in {"subscribe", "all"}:
        if ctx.mode == "skipped_expired" and not subscribe_rows:
            subscribe_rows = [{"status": "skipped", "reason": "申购时段已过，不执行申购"}]
        result["subscribe"] = subscribe_rows
    if ctx.phase in {"subscribe", "all"}:
        result["today_entrusts_count"] = len(today_entrusts)
        result["today_entrusts_error"] = entrust_error
    if ctx.phase in {"allotment", "all"}:
        result["allotment"] = allotment_rows
        result["allotment_error"] = allotment_error
    return _safe_value(result)


def _effective_mode(cfg: Mapping[str, Any], day: str, live: bool) -> str:
    if not live or (cfg.get("execution") or {}).get("mode") != "live":
        return "dry_run"
    from execution.subscribe import live_run_allowed

    return "live" if live_run_allowed(day) else "skipped_expired"


def _phase_names(phase: str) -> tuple[str, ...]:
    if phase == "all":
        return ("login", "subscribe", "allotment")
    if phase in {"login", "subscribe", "allotment"}:
        return (phase,)
    raise ValueError("phase 仅支持 login/subscribe/allotment/all")


def _account_identity(ths_row: Mapping[str, Any], fund_row: Mapping[str, Any]) -> dict[str, Any]:
    return account_identity(str(ths_row.get("username") or ""), fund_row)


def _account_label(ths_row: Mapping[str, Any], fund_row: Mapping[str, Any]) -> str:
    return _account_identity(ths_row, fund_row)["display_name"]


def _sync_phase_rows(ths_row: dict[str, Any]) -> None:
    for phase in ("subscribe", "allotment"):
        rows: list[dict[str, Any]] = []
        for fund_row in ths_row.get("fund_accounts", []):
            identity = _account_identity(ths_row, fund_row)
            phase_rows = fund_row.get(phase, [])
            for item in phase_rows if isinstance(phase_rows, list) else [phase_rows]:
                if isinstance(item, Mapping):
                    row = {**identity, **dict(item)}
                    row.setdefault("account", identity["display_name"])
                    rows.append(_safe_value(row))
        ths_row[phase] = rows


def _phase_items(result: Mapping[str, Any], phase: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for ths_row in result.get("ths_accounts", []):
        for fund_row in ths_row.get("fund_accounts", []):
            identity = _account_identity(ths_row, fund_row)
            if phase == "login":
                login_status = str(fund_row.get("login_status") or fund_row.get("status") or "")
                items.append(_safe_value({
                    **identity,
                    "login_status": login_status,
                    "status": login_status,
                    "dialog_required": bool(fund_row.get("dialog_required")),
                    "manual_required": bool(fund_row.get("manual_required")),
                    "error_code": fund_row.get("error_code", ""),
                    "error": fund_row.get("error", ""),
                }))
                continue
            phase_rows = fund_row.get(phase, [])
            for raw in phase_rows if isinstance(phase_rows, list) else [phase_rows]:
                if not isinstance(raw, Mapping):
                    continue
                if phase == "subscribe":
                    item = {
                        **identity,
                        "account": identity["display_name"],
                        "name": raw.get("name"),
                        "apply_code": raw.get("apply_code"),
                        "amount": raw.get("amount"),
                        "unit": raw.get("unit"),
                        "status": raw.get("status"),
                        "reason": raw.get("reason"),
                    }
                else:
                    item = {
                        **identity,
                        "account": identity["display_name"],
                        "name": raw.get("证券名称") or raw.get("新股名称") or raw.get("name"),
                        "apply_code": raw.get("证券代码") or raw.get("新股代码") or raw.get("apply_code"),
                        "winning_qty": raw.get("中签数量") or raw.get("中签股数") or raw.get("中签张数") or raw.get("winning_qty"),
                        "payment_amount": raw.get("缴款金额") or raw.get("中签金额") or raw.get("payment_amount"),
                        "status": raw.get("status") or "won",
                    }
                items.append(_safe_value(item))
    if phase == "login":
        return unique_account_items(items)
    if phase == "allotment":
        seen: set[tuple[str, str]] = set()
        unique: list[dict[str, Any]] = []
        for item in items:
            key = (str(item.get("account") or ""), str(item.get("apply_code") or ""))
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique
    return items


def run_ths_account_workflow(
    cfg: Mapping[str, Any],
    *,
    day: str | None = None,
    live: bool = False,
    phase: str = "all",
    ui_factory: Callable[[ClientSpec, dict], Any] | None = None,
    lifecycle_factory: Callable[[ClientSpec, dict], Any] | None = None,
    lock_factory: Callable[[str], Any] | None = None,
    account_switcher: Callable[..., Any] = switch_ths_account,
    password_reader: Callable[[str], str] = read_ths_password,
    account_task: Callable[[ThsAccountTaskContext], Mapping[str, Any]] = default_account_task,
    result_writer: Callable[[Mapping[str, Any]], None] | None = None,
    receipt_sender: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
    force_retry: bool = False,
) -> dict[str, Any]:
    """两个层级严格串行；phase 分流，任何单户失败不阻断，最终温和退出。"""
    phase_names = _phase_names(str(phase))
    config = dict(cfg or {})
    business_day = day or date.today().isoformat()
    mode_cfg = load_ths_account_mode(config)
    gui = (config.get("gui") or {}).get("ths_account_switch") or {}
    writer = result_writer or default_result_writer(business_day)
    receipt = receipt_sender or default_receipt_sender
    effective_mode = _effective_mode(config, business_day, bool(live))
    result: dict[str, Any] = {
        "day": business_day,
        "phase": str(phase),
        "mode": effective_mode,
        "status": "running",
        "ths_accounts": [],
        "result_write_errors": [],
        "receipt_errors": [],
        "close_errors": [],
        "error_code": "",
        "error": "",
    }
    overall_t0 = time.monotonic()

    def write_now() -> None:
        try:
            writer(_safe_value(result))
        except Exception:
            result["result_write_errors"].append({
                "status": "failed",
                "error_code": "RESULT_WRITE_FAILED",
                "error": "结果即时落盘失败",
            })

    def send_receipts() -> None:
        for kind in phase_names:
            if kind == "login":
                login_items = _phase_items(result, "login")
                payload = {
                    "date": business_day,
                    "summary": {"phase": kind, "accounts": len(login_items)},
                    "clients": [{
                        "client_id": "ths_account_switch",
                        "accounts": login_items,
                    }],
                    "items": login_items,
                    "next_action": "失败账户按状态和原因人工核对。",
                }
            else:
                payload = {
                    "date": business_day,
                    "summary": {"phase": kind},
                    "items": _phase_items(result, kind),
                    "next_action": (
                        "中签账户请在缴款截止时间前确保可用资金足额。"
                        if kind == "allotment"
                        else "失败或不确定项人工核对当日委托，禁止重复提交。"
                    ),
                }
            write_now()
            try:
                receipt(kind, _safe_value(payload))
            except Exception as exc:
                result["receipt_errors"].append({"kind": kind, **_error_row(exc)})
            write_now()

    enabled = [item for item in mode_cfg.accounts if item.enabled]
    limit = min(int(mode_cfg.max_ths_accounts), MAX_THS_LOGIN_ACCOUNTS)
    accounts = enabled[:limit]
    client = ClientSpec(
        client_id="ths_account_switch",
        hexin_path=mode_cfg.hexin_path,
        xiadan_path=mode_cfg.xiadan_path,
    )
    factory = ui_factory or (
        lambda spec, cfg: __import__(
            "execution.ths_account_ui", fromlist=["ThsAccountUI"]
        ).ThsAccountUI(
            spec,
            cfg,
            known_ths_accounts=[item.username for item in accounts],
        )
    )
    seen_funds: set[str] = set()
    switch_timeout = float(gui.get("restart_timeout_s", 0)) + float(gui.get("login_wait_s", 0))
    lock = (lock_factory or gui_lock)("ths_account_switch")
    lifecycle_closes: list[dict[str, Any]] = []
    any_started = False

    def close_session(ui_obj: Any, lifecycle_obj: Any) -> dict[str, Any]:
        can_close_ui = ui_obj is not None and callable(getattr(ui_obj, "close_main_window", None)) and callable(
            getattr(ui_obj, "click_popup", None)
        )
        if can_close_ui:
            try:
                close_ths_client(ui_obj)
            except Exception as exc:
                result["close_errors"].append(_error_row(exc))
        try:
            close_state = _result_dict(lifecycle_obj.close())
        except Exception as exc:
            close_state = _error_row(exc, "close_failed")
        lifecycle_closes.append(_safe_value(close_state))
        return close_state

    def process_account(configured: Any) -> None:
        nonlocal any_started
        target = ThsLoginAccount(username=configured.username)
        ths_row: dict[str, Any] = {
            "username": configured.username,
            "status": "running",
            "switch_status": "",
            "fund_accounts": [],
            "fund_limit_reached": False,
            "error_code": "",
            "error": "",
        }
        result["ths_accounts"].append(ths_row)
        account_t0 = time.monotonic()
        lifecycle_obj = (lifecycle_factory or (lambda spec, cfg: GentleClientLifecycle(spec, cfg)))(
            client, dict(config)
        )
        ui_obj = None
        started = False
        try:
            try:
                lifecycle_obj.start()
                started = True
                any_started = True
            except Exception as exc:
                ths_row.update(_error_row(exc, "switch_failed"))
                ths_row["error_code"] = "THS_WORKFLOW_START_FAILED"
                write_now()
                return

            ui_obj = factory(client, dict(config))
            switched = account_switcher(
                target,
                client,
                lambda name=configured.username: password_reader(name),
                ui_obj,
                switch_timeout,
            )
            ths_row["switch_status"] = _result_dict(switched).get("status", "switched")

            fund_limit = int(mode_cfg.max_fund_accounts_per_ths)
            _sw = (dict(config).get("gui") or {}).get("ths_account_switch", {})
            per_fund_timeout_s = float(_sw.get("fund_login_timeout_s", _sw.get("per_fund_timeout_s", 15)) or 15)
            fund_total_timeout_s = float(_sw.get("fund_total_timeout_s", 45) or 45)
            refs = list(ui_obj.discover_fund_accounts())[:fund_limit]
            ready_count = 0
            for ref in refs:
                safe_ref = ref.safe_dict() if hasattr(ref, "safe_dict") else _safe_value(dict(ref))
                identity = str(
                    getattr(ref, "fund_account_hash", "")
                    or getattr(ref, "key", "")
                    or safe_ref.get("target_key", "")
                )
                if identity in seen_funds:
                    row = {**safe_ref, "status": "duplicate_account",
                           "error_code": "DUPLICATE_FUND_ACCOUNT", "error": "same fund account already processed"}
                    ths_row["fund_accounts"].append(row)
                    _sync_phase_rows(ths_row)
                    write_now()
                    continue
                seen_funds.add(identity)
                fund_t0 = time.monotonic()
                login_t0 = fund_t0
                # 2026-10-27 线程看门狗：每户（登录+任务）整体硬限时。此前 _sleep 包裹盖不住
                # OCR 子进程/win32 阻塞调用（实战卡在每户 10 分钟+），必须线程级 join 超时。
                box: dict[str, Any] = {}

                def _process_one() -> None:
                    try:
                        if hasattr(ui_obj, "start_deadline"):
                            ui_obj.start_deadline(per_fund_timeout_s)
                        box["login"] = _result_dict(ui_obj.login_fund_account(ref))
                        if hasattr(ui_obj, "clear_deadline"):
                            ui_obj.clear_deadline()
                        box["login_done"] = True
                    except Exception as exc:  # noqa: BLE001
                        box["login_error"] = exc
                        box["login"] = None
                        box["login_done"] = True
                        return
                    login_status_inner = str((box["login"] or {}).get("status") or "")
                    if login_status_inner in {"ready", "already_logged_in"} and phase != "login":
                        try:
                            box["task"] = _result_dict(account_task(ThsAccountTaskContext(
                                day=business_day,
                                live=effective_mode == "live",
                                mode=effective_mode,
                                phase=str(phase),
                                force_retry=bool(force_retry),
                                ths_username=configured.username,
                                fund_account=dict(box["login"]),
                                client=client,
                                cfg=dict(config),
                            )))
                        except Exception as exc:  # noqa: BLE001
                            box["task_error"] = exc

                worker = threading.Thread(target=_process_one, daemon=True)
                worker.start()
                # 两段式 join：先给登录预算（per_fund_timeout_s），登录成功再给任务追加预算。
                # 避免登录 12s + 任务 27s 的合法组合被 30s 整体限时误杀。
                worker.join(max(5.0, float(per_fund_timeout_s)))
                if box.get("login_done") and phase != "login":
                    _elapsed = time.monotonic() - fund_t0
                    worker.join(max(5.0, float(fund_total_timeout_s) - _elapsed))
                if not box.get("login_done"):
                    # 整体超时：孤儿线程弃置（daemon），GUI 状态由下一户前置清理复位
                    try:
                        if hasattr(ui_obj, "clear_deadline"):
                            ui_obj.clear_deadline()
                    except Exception:
                        pass
                    try:
                        close_modal_dialogs(client=client)
                    except Exception:
                        pass
                    login_result = {**safe_ref, "status": "timeout",
                                    "error_code": "FUND_ACCOUNT_TIMEOUT",
                                    "error": f"资金户处理超过硬限时 {per_fund_timeout_s:g}s（含阻塞调用），判失败跳下一户"}
                else:
                    if box.get("login") is not None:
                        login_result = box["login"]
                        if getattr(box.get("login_error"), "code", "") == "FUND_ACCOUNT_TIMEOUT":
                            login_result["status"] = "timeout"
                    else:
                        exc = box.get("login_error")
                        login_result = {**safe_ref, **_error_row(exc)}
                        if getattr(exc, "code", "") == "FUND_ACCOUNT_TIMEOUT":
                            login_result["status"] = "timeout"
                if hasattr(ui_obj, "clear_deadline"):
                    try:
                        ui_obj.clear_deadline()
                    except Exception:
                        pass
                if "xiadan" in f"{login_result.get('error_code', '')} {login_result.get('error', '')}".lower():
                    login_result["status"] = "xiadan_failed"
                login_status = str(login_result.get("status") or "failed")
                row = {**safe_ref, **login_result,
                       "login_status": login_status, "task_status": "not_run",
                       "status": login_status,
                       "login_duration_s": round(time.monotonic() - login_t0, 1)}
                task_result = box.get("task")
                if box.get("login_done") and login_status in {"ready", "already_logged_in"}:
                    ready_count += 1
                    if phase == "login":
                        row["status"] = "completed"
                    elif task_result is not None:
                        try:
                            task_t0 = fund_t0
                            for key in ("subscribe", "allotment"):
                                if key in phase_names and key in task_result:
                                    row[key] = task_result[key]
                            row["task_status"] = str(task_result.get("status") or "completed")
                            row["task_duration_s"] = round(time.monotonic() - task_t0, 1)
                            row["status"] = (
                                "completed" if row["task_status"] == "skipped_expired"
                                else row["task_status"]
                            )
                            for key in ("today_entrusts_count", "today_entrusts_error", "allotment_error"):
                                if key in task_result:
                                    row[key] = task_result[key]
                            if task_result.get("stage_durations_s"):
                                row["stage_durations_s"] = task_result["stage_durations_s"]
                        except Exception as exc:
                            row.update(_error_row(exc))
                            row["task_status"] = "failed"
                row["duration_s"] = round(time.monotonic() - fund_t0, 1)
                ths_row["fund_accounts"].append(row)
                _sync_phase_rows(ths_row)
                write_now()
                if ready_count >= fund_limit or len(ths_row["fund_accounts"]) >= fund_limit:
                    break

            ths_row["fund_limit_reached"] = len(ths_row["fund_accounts"]) >= fund_limit
            rows = ths_row["fund_accounts"]
            failed = any(row.get("status") not in {"completed", "duplicate_account"} for row in rows)
            if rows and all(row.get("status") == "xiadan_failed" for row in rows):
                ths_row["status"] = "xiadan_failed"
                ths_row["error_code"] = "XIADAN_MISSING"
                ths_row["error"] = "xiadan account list unavailable or F12 startup failed"
            else:
                ths_row["status"] = "partial" if failed else "completed"
            _sync_phase_rows(ths_row)
            write_now()
        except Exception as exc:
            ths_row.update(_error_row(exc, "failed"))
            write_now()
        finally:
            ths_row["duration_s"] = round(time.monotonic() - account_t0, 1)
            close_state = close_session(ui_obj, lifecycle_obj)
            result["lifecycle_close"] = _safe_value(close_state)
            if result["close_errors"] or close_state.get("status") == "close_failed":
                result["status"] = "partial"
            write_now()

    try:
        with lock:
            for configured in accounts:
                process_account(configured)
    finally:
        result["lifecycle_closes"] = lifecycle_closes
        startup_failed = next((row for row in result["ths_accounts"] if row.get("error_code") == "THS_WORKFLOW_START_FAILED"), None)
        if startup_failed:
            result["status"] = "failed"
            result["error_code"] = "THS_WORKFLOW_START_FAILED"
            result["error"] = startup_failed.get("error") or "THS session startup failed"
        elif any(row.get("status") != "completed" for row in result["ths_accounts"]):
            result["status"] = "partial"
        elif result["status"] == "running":
            result["status"] = "completed"
        result["duration_s"] = round(time.monotonic() - overall_t0, 1)
        write_now()
        if any_started:
            send_receipts()
    return _safe_value(result)
