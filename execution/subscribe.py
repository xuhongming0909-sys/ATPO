# AI-SUMMARY: 申购 allowlist 执行与买入表单兜底——逐笔订单台账、F8 核验、不确定状态禁止重试；批量申购页未覆盖标的回退本模块
from shared.errors import AutoIpoError, sanitize_sensitive_text

CB_PRICE = 100.0
CB_TOP_SZ = 10000  # 深市可转债顶格：1 万张
CB_TOP_SH = 1000   # 沪市可转债顶格：1000 手

def _cb_amount(bond_code: str) -> tuple[int, str]:
    return (CB_TOP_SH, "手") if str(bond_code).startswith("11") else (CB_TOP_SZ, "张")


def _blacklist_codes(blacklist) -> set[str]:
    items = [blacklist] if isinstance(blacklist, (str, dict)) else list(blacklist or [])
    codes = set()
    for item in items:
        value = item.get("apply_code") or item.get("code") if isinstance(item, dict) else item
        code = str(value or "").replace(" ", "")
        if code:
            codes.add(code)
    return codes


def calendar_allowlist(cal: dict, blacklist=None) -> list[dict]:
    """生成当日唯一申购 allowlist；permissions 不过滤，blacklist 直接排除。"""
    blocked = _blacklist_codes(blacklist)
    orders: list[dict] = []
    for c in cal.get("cbs", []):
        if str(c.get("apply_code", "")).replace(" ", "") in blocked:
            continue
        amount, unit = _cb_amount(c["code"])
        order = {"kind": "可转债", "name": c["name"], "apply_code": c["apply_code"],
                 "price": CB_PRICE, "amount": amount, "unit": unit}
        orders.append(order)
    for s in cal.get("new_stocks", []):
        if str(s.get("apply_code", "")).replace(" ", "") in blocked:
            continue
        order = {"kind": "新股", "name": s["name"], "apply_code": s["apply_code"],
                 "price": s.get("issue_price"), "amount": s.get("apply_limit"), "unit": "股"}
        if not s.get("issue_price"):
            order.update(skip=True, reason="发行价未定")
        elif not s.get("apply_limit"):
            order.update(skip=True, reason="申购上限未知")
        orders.append(order)
    return orders


_UNIQUE_KEYS = ("entrust_no", "entrust_id", "委托编号", "合同编号", "业务编号", "unique_key")
_QUANTITY_KEYS = ("委托数量", "申购数量", "申请数量", "数量")
_STATUS_KEYS = ("委托状态", "状态", "状态说明", "备注", "废单原因")
_REJECT_WORDS = ("废单", "拒绝", "失败", "撤单", "作废", "无效")

def _field(row: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _unique_keys(value) -> set[str]:
    if not isinstance(value, dict):
        return set()
    return {_field(value, (key,)) for key in _UNIQUE_KEYS if _field(value, (key,))}


def _entrust_quantity(row: dict) -> float | None:
    raw = _field(row, _QUANTITY_KEYS)
    if not raw:
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _expected_quantity(order: dict) -> float | None:
    raw = _field(order, ("amount",) + _QUANTITY_KEYS)
    if not raw:
        return None
    try:
        return float(str(raw).replace(",", ""))
    except ValueError:
        return None


def _rejected(row: dict) -> bool:
    text = " ".join(str(row.get(key, "")) for key in _STATUS_KEYS)
    return any(word in text for word in _REJECT_WORDS)


def _status_value(value) -> str:
    if isinstance(value, dict):
        return _field(value, _STATUS_KEYS)
    return _field({"status": value}, ("status",))


def _matches_identity(row: dict, order: dict) -> bool:
    code = str(order.get("apply_code") or "").replace(" ", "")
    name = str(order.get("name") or "")
    row_code = str(row.get("证券代码", "")).replace(" ", "")
    row_name = str(row.get("证券名称", ""))
    return bool((code and code == row_code) or (name and name == row_name))


def verify_entrust(user, order: dict, entrust_rows=None):
    """F8 \u5f53\u65e5\u59d4\u6258\u4e25\u683c\u6838\u9a8c\uff1aTrue=\u552f\u4e00\u4e14\u4e00\u81f4\uff0cFalse=\u4e0d\u4e00\u81f4\uff0cNone=\u67e5\u8be2\u5931\u8d25\u3002"""
    if entrust_rows is None:
        try:
            from execution.ths_client import read_today_entrusts_via_ocr
            entrust_rows = read_today_entrusts_via_ocr(user)
            if entrust_rows is None:
                return None
        except Exception:
            return None
    rows = [row for row in entrust_rows if isinstance(row, dict) and _matches_identity(row, order)]
    if not rows:
        return False
    expected_key = _unique_keys(order)
    keyed_rows = [row for row in rows if _unique_keys(row)]
    if expected_key:
        rows = [row for row in rows if _unique_keys(row) & expected_key]
    elif keyed_rows:
        return False
    if len(rows) != 1:
        return False
    row = rows[0]
    expected_qty = _expected_quantity(order)
    actual_qty = _entrust_quantity(row)
    if expected_qty is not None and actual_qty is not None and expected_qty != actual_qty:
        return False
    expected_status = _status_value(order.get("client_return"))
    actual_status = _status_value(row)
    if expected_status and actual_status and expected_status != actual_status:
        return False
    return not _rejected(row)

def _emit_result(result_sink, result: dict) -> None:
    if result_sink is None:
        return
    try:
        result_sink(dict(result))
    except AutoIpoError:
        raise
    except Exception as exc:
        raise AutoIpoError(
            "RESULT_WRITE_FAILED",
            "申购结果写盘失败，已停止后续提交",
            "检查磁盘/权限和 runtime_data/results；已生成订单须先人工核对当日委托",
            {"detail": sanitize_sensitive_text(exc)},
        ) from None


def live_run_allowed(day: str, now=None) -> bool:
    from datetime import datetime, time
    from shared.config import load_config
    current = now or datetime.now()
    if current.date().isoformat() != day:
        return False
    window = (load_config().get("schedule", {}).get("subscribe_window") or ["09:30", "15:00"])
    return time.fromisoformat(window[0]) <= current.time() < time.fromisoformat(window[1])


def _is_bse_code(code) -> bool:
    """北交所代码段：920xxx 新段及 43/83/87/88 开头存量段；买入表单无板块切换，禁止单笔下。"""
    text = str(code or "").replace(" ", "")
    return text.startswith(("920", "43", "83", "87", "88"))


def _is_stale_handle_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "not a vaild window handle" in text or "not a valid window handle" in text


def execute(user, orders: list[dict], mode: str, ledger=None, account_id: str = "",
            account_key: str | None = None, client_id: str = "", client=None,
            result_sink=None) -> list[dict]:
    """dry_run 只生成结果；live 每账户+代码+日期最多一次提交，不确定结果禁止重试。"""
    import time
    results = []
    for o in orders:
        if o.get("skip"):
            result = {**o, "status": "skipped", "client_id": client_id,
                      "verified": None, "error_code": "", "error": ""}
            results.append(result)
            _emit_result(result_sink, result)
            continue
        if mode != "live":
            result = {**o, "status": "dry_run", "client_id": client_id,
                      "verified": None, "error_code": "", "error": ""}
            results.append(result)
            _emit_result(result_sink, result)
            continue
        if _is_bse_code(o.get("apply_code")):
            result = {**o, "status": "skipped", "client_id": client_id,
                      "reason": "北交所代码不走买入表单（无板块切换），需批量申购页或人工",
                      "verified": None, "error_code": "BSE_SINGLE_FORM_UNSUPPORTED", "error": ""}
            results.append(result)
            _emit_result(result_sink, result)
            continue
        if ledger is not None and not ledger.begin(account_id, o, account_key=account_key, client_id=client_id):
            current = ledger.get(account_id, o["apply_code"], account_key=account_key) or {}
            result = {**o, "status": "skipped", "client_id": client_id,
                      "reason": f"当日已尝试过：{current.get('status', 'unknown')}",
                      "verified": None, "error_code": "ORDER_ALREADY_ATTEMPTED", "error": ""}
            results.append(result)
            _emit_result(result_sink, result)
            continue
        try:
            try:
                user._dismiss_price_format_dialog()
            except Exception:
                pass
            ret = user.buy(o["apply_code"], o["price"], o["amount"])
            try:
                user._dismiss_price_format_dialog()
            except Exception:
                pass
            try:
                from execution.ths_client import read_today_entrusts_via_ocr
                rows = read_today_entrusts_via_ocr(user)
                if rows is None:
                    raise RuntimeError("F8 \u5f53\u65e5\u59d4\u6258 OCR \u8bfb\u53d6\u5931\u8d25")
                entrust_error = ""
            except Exception as exc:
                if client is not None and _is_stale_handle_error(exc):
                    try:
                        from execution.ths_client import connect, read_today_entrusts_via_ocr

                        user = connect(client=client)
                        rows = read_today_entrusts_via_ocr(user)
                        if rows is None:
                            raise RuntimeError("F8 \u5f53\u65e5\u59d4\u6258 OCR \u8bfb\u53d6\u5931\u8d25")
                        entrust_error = ""
                    except Exception as exc2:
                        rows = None
                        entrust_error = sanitize_sensitive_text(exc2)
                else:
                    rows = None
                    entrust_error = sanitize_sensitive_text(exc)
            verified = (None if rows is None else
                        verify_entrust(user, {**o, "client_return": ret}, entrust_rows=rows))
            status = "submitted" if verified else "submitted_unverified"
            if verified:
                reason, error_code, error = "", "", ""
            elif rows is None:
                reason = "F8 查询失败，提交结果未核验"
                error_code = "IPO_ENTRUST_QUERY_FAILED"
                error = f"{reason}：{entrust_error}" if entrust_error else reason
            else:
                reason = "F8 当日委托唯一键/数量/状态不一致或未确认"
                error_code = "IPO_ENTRUST_MISMATCH"
                error = reason
            result = {**o, "status": status, "client_return": ret, "client_id": client_id,
                      "verified": verified, "attempts": 1, "reason": reason,
                      "error_code": error_code, "error": error}
            results.append(result)
            if ledger is not None:
                ledger.mark(account_id, o, status, account_key=account_key, client_id=client_id,
                            reason=reason, error_code=error_code, error=error, verified=verified)
            _emit_result(result_sink, result)
        except Exception as e:
            if isinstance(e, AutoIpoError) and e.code == "RESULT_WRITE_FAILED":
                raise
            text = sanitize_sensitive_text(e)[:200]
            status = "failed_confirmed" if "提交失败" in text else "unknown"
            result = {**o, "status": status, "reason": text, "attempts": 1, "client_id": client_id,
                      "verified": False if status == "failed_confirmed" else None,
                      "error_code": "ORDER_REJECTED" if status == "failed_confirmed" else "ORDER_RESULT_UNCONFIRMED",
                      "error": text}
            results.append(result)
            if ledger is not None:
                ledger.mark(account_id, o, status, account_key=account_key, client_id=client_id,
                            reason=text, error_code=result["error_code"], error=text,
                            verified=result["verified"])
            _emit_result(result_sink, result)
        finally:
            from execution.login import close_modal_dialogs
            close_modal_dialogs(client=client)
        time.sleep(0.1)
    return results


def _login_failed_results(orders: list[dict], err: Exception) -> list[dict]:
    reason = f"登录/连接失败：{sanitize_sensitive_text(err)[:150]}"
    return [{**o, "status": "skipped"} if o.get("skip")
            else {**o, "status": "failed", "reason": reason} for o in orders]


def _notify_results(day: str, all_results: list[dict]) -> str:
    from notification.receipts import send_receipt
    success_statuses = {"submitted", "success", "ok"}
    skipped_statuses = {"skipped", "duplicate_account", "dry_run", "expired"}
    summary = {"success": 0, "skipped": 0, "failed": 0}
    items = []
    for account in all_results:
        account_name = account.get("label") or account.get("display_name") or "未知账户"
        for item in account.get("results", []):
            status = str(item.get("status", "")).lower()
            bucket = "success" if status in success_statuses else "skipped" if status in skipped_statuses else "failed"
            summary[bucket] += 1
            items.append({key: item.get(key) for key in
                          ("name", "apply_code", "amount", "unit", "status", "reason")
                          if item.get(key) not in (None, "")} | {"account": account_name})
    next_action = ("失败或不确定项人工核对当日委托，禁止重复提交。"
                   if summary["failed"] else "跳过项无需处理。")
    try:
        result = send_receipt("subscribe", {"date": day, "summary": summary, "items": items, "next_action": next_action})
        if isinstance(result, dict) and result.get("sent") is False:
            return "skipped" if result.get("reason") == "disabled" else "failed"
        return "sent"
    except Exception:
        return "failed"


def uncovered_orders(orders: list[dict], batch_results: list[dict]) -> list[dict]:
    covered = set()
    for item in batch_results:
        code = str(item.get("apply_code") or "")
        name = str(item.get("name") or "")
        if code:
            covered.add(code)
        if name:
            covered.add(name)
    return [o for o in orders if not o.get("skip")
            and str(o.get("apply_code") or "") not in covered
            and str(o.get("name") or "") not in covered]




