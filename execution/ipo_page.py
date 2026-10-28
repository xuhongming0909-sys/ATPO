# AI-SUMMARY: 批量新股申购页——只提交当日 calendar allowlist 且未命中 blacklist 的网格行，未知/歧义整批拒绝
import time

from execution.ths_client import _find_ctrl
from shared.errors import sanitize_sensitive_text, sanitize_sensitive_value

MENU_PATH = ["新股申购", "批量新股申购"]
SELECT_ALL_CTRL = 1098  # 全部选中
SUBMIT_CTRL = 1006      # 申购
GRID_CTRL = 1047        # COMMON_GRID_CONTROL_ID
ROW_LEFT_MARGIN = 50
ROW_FIRST_HEIGHT = 30
ROW_HEIGHT = 16

_QUOTA_KEYS = ("申购数量", "可申购数量", "申购上限")
_CODE_KEYS = ("apply_code", "新股代码", "申购代码", "证券代码", "代码", "code")
_NAME_KEYS = ("name", "新股名称", "证券名称")


def read_ipo_grid(user, attempts: int = 2, interval_s: float = 0.2) -> list[dict]:
    """导航到批量申购页并屏幕 OCR 读网格（不碰剪贴板，不触发拷贝验证码）。"""
    from execution.ths_client import read_grid_via_ocr

    user._switch_left_menus(MENU_PATH)
    rows: list[dict] = []
    attempts = max(1, int(attempts))
    for attempt in range(attempts):
        read = read_grid_via_ocr(user, GRID_CTRL, ("\u65b0\u80a1\u4ee3\u7801", "\u7533\u8d2d\u4ee3\u7801", "\u8bc1\u5238\u4ee3\u7801", "\u4ee3\u7801"))
        if read is None:
            if attempt + 1 < attempts:
                time.sleep(interval_s)
            continue
        rows = read
        if rows and all(_code(row) for row in rows):
            break
        if attempt + 1 < attempts:
            time.sleep(interval_s)
    return rows


def _quota(row: dict) -> float:
    for k in _QUOTA_KEYS:
        try:
            return float(str(row.get(k, "")).replace(",", ""))
        except (TypeError, ValueError):
            continue
    return 0.0


def _value(row: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _code(row: dict) -> str:
    return _value(row, _CODE_KEYS).replace(" ", "")


def _name(row: dict) -> str:
    return _value(row, _NAME_KEYS)


def _allow_items(allowlist) -> tuple[list[dict], str]:
    if allowlist is None:
        return [], "IPO_ALLOWLIST_MISSING"
    if isinstance(allowlist, dict):
        allowlist = [allowlist]
    try:
        items = list(allowlist)
    except TypeError:
        return [], "IPO_ALLOWLIST_INVALID"
    if not items:
        return [], "IPO_ALLOWLIST_MISSING"
    result = []
    for item in items:
        if isinstance(item, str):
            item = {"apply_code": item}
        if not isinstance(item, dict):
            return [], "IPO_ALLOWLIST_INVALID"
        code = _code(item)
        if not code:
            return [], "IPO_ALLOWLIST_INVALID"
        result.append(item)
    return result, ""


def _blacklist_codes(blacklist) -> set[str]:
    if blacklist is None:
        return set()
    if isinstance(blacklist, (str, dict)):
        blacklist = [blacklist]
    codes = set()
    for item in blacklist:
        codes.add(_code(item) if isinstance(item, dict) else str(item).strip().replace(" ", ""))
    return {code for code in codes if code}


def _result(order: dict, status: str, *, reason: str = "", error_code: str = "",
            verified: bool | None = None, client_id: str = "") -> dict:
    result = dict(order)
    result.update(
        status=status,
        reason=sanitize_sensitive_text(reason),
        error_code=error_code,
        error=sanitize_sensitive_text(reason) if error_code else "",
        verified=verified,
        client_id=client_id,
    )
    return result


def _reject_batch(rows: list[dict], code: str, reason: str, client_id: str) -> list[dict]:
    return [_result(_order_from_row(row), "batch_rejected", reason=reason,
                    error_code=code, client_id=client_id) for row in rows]


def _order_from_row(row: dict) -> dict:
    return {
        "name": _name(row),
        "apply_code": _code(row),
        "amount": _quota(row),
        "unit": "",
    }


def _click_grid_row(user, row_idx: int) -> None:
    grid = _find_ctrl(user._main, GRID_CTRL, "CVirtualGridCtrl")
    grid.click(coords=(ROW_LEFT_MARGIN, ROW_FIRST_HEIGHT + ROW_HEIGHT * row_idx))


def _click_button(user, control_id: int) -> None:
    _find_ctrl(user._main, control_id, "Button").click()


def _matches_entrust(row: dict, order: dict) -> bool:
    code = str(order.get("apply_code") or "")
    name = str(order.get("name") or "")
    return bool((code and code in str(row.get("证券代码", ""))) or
                (name and name in str(row.get("证券名称", ""))))


def batch_subscribe(user, ledger=None, account_id: str = "", account_key: str | None = None,
                    client_id: str = "", allowlist=None, blacklist=None, dry_run: bool = False) -> list[dict]:
    """一键批量申购：只提交 calendar allowlist 且未命中 blacklist 的行。

    任何网格行无法唯一映射到当日 allowlist 时整批拒绝；permissions 不参与本路径过滤。
    """
    rows = read_ipo_grid(user)
    if not rows:
        return []
    allow_items, allow_error = _allow_items(allowlist)
    if allow_error:
        return _reject_batch(rows, allow_error, "当日 calendar allowlist 不可用，整批拒绝", client_id)
    allow_index: dict[str, list[dict]] = {}
    for item in allow_items:
        allow_index.setdefault(_code(item), []).append(item)
    if any(len(items) != 1 for items in allow_index.values()):
        return _reject_batch(rows, "IPO_ALLOWLIST_AMBIGUOUS", "calendar allowlist 存在重复代码，整批拒绝", client_id)

    seen: set[str] = set()
    for row in rows:
        code = _code(row)
        if not code or code in seen:
            return _reject_batch(rows, "IPO_GRID_DUPLICATE_CODE", "网格代码为空或重复，整批拒绝", client_id)
        seen.add(code)
        if code not in allow_index:
            return _reject_batch(rows, "IPO_GRID_UNKNOWN_ROW", "网格行未命中当日 calendar allowlist，整批拒绝", client_id)

    blocked_codes = _blacklist_codes(blacklist)
    results: list[dict] = []
    invalid_idx: list[int] = []
    pending: list[dict] = []
    for i, row in enumerate(rows):
        code = _code(row)
        item = allow_index[code][0]
        order = _order_from_row(row)
        if item.get("name"):
            order["name"] = str(item["name"])
        if code in blocked_codes:
            invalid_idx.append(i)
            results.append(_result(order, "skipped", reason="命中当日 blacklist",
                                   error_code="IPO_BLACKLISTED", client_id=client_id))
            continue
        if _quota(row) <= 0:
            invalid_idx.append(i)
            results.append(_result(order, "skipped", reason="可申购额度为0（无权限/无市值）",
                                   error_code="IPO_QUOTA_ZERO", client_id=client_id))
            continue
        if dry_run:
            results.append(_result(order, "dry_run", client_id=client_id))
            continue
        if ledger is not None:
            try:
                accepted = ledger.begin(account_id, order, account_key=account_key, client_id=client_id)
            except Exception as exc:
                return _reject_batch(rows, "IPO_LEDGER_WRITE_FAILED",
                                     f"订单台账写入失败，整批拒绝：{sanitize_sensitive_text(exc)}", client_id)
            if not accepted:
                current = ledger.get(account_id, code, account_key=account_key) or {}
                invalid_idx.append(i)
                results.append(_result(order, "skipped",
                                       reason=f"当日已尝试过：{current.get('status', 'unknown')}",
                                       error_code="IPO_ALREADY_ATTEMPTED", client_id=client_id))
                continue
        result = _result(order, "pending", client_id=client_id)
        results.append(result)
        pending.append(result)

    if not pending:
        return results
    try:
        _click_button(user, SELECT_ALL_CTRL)
        time.sleep(0.1)
        for i in invalid_idx:
            _click_grid_row(user, i)
            time.sleep(0.1)
    except Exception as exc:
        text = sanitize_sensitive_text(exc)
        for result in pending:
            result.update(status="batch_rejected", reason=f"提交前 UI 操作失败，未提交：{text}",
                          error_code="IPO_UI_PRE_SUBMIT_FAILED", error=text, verified=False)
            if ledger is not None:
                try:
                    ledger.mark(account_id, result, "batch_rejected", account_key=account_key,
                                client_id=client_id, reason=result["reason"],
                                error_code=result["error_code"], error=text, verified=False)
                except Exception:
                    pass
        return results

    try:
        _click_button(user, SUBMIT_CTRL)
    except Exception as exc:
        text = sanitize_sensitive_text(exc)
        for result in pending:
            result.update(status="unknown", reason=f"申购提交结果未知：{text}",
                          error_code="IPO_SUBMIT_UNKNOWN", error=text, verified=None)
            if ledger is not None:
                try:
                    ledger.mark(account_id, result, "unknown", account_key=account_key,
                                client_id=client_id, reason=result["reason"],
                                error_code=result["error_code"], error=text, verified=None)
                except Exception:
                    pass
        return results

    try:
        ret = user._handle_pop_dialogs()
        message = sanitize_sensitive_value((ret or {}).get("message", "success") if isinstance(ret, dict) else ret)
    except Exception as exc:
        message = sanitize_sensitive_text(exc)
    try:
        from execution.ths_client import read_today_entrusts_via_ocr
        entrust_rows = read_today_entrusts_via_ocr(user)
        if entrust_rows is None:
            raise RuntimeError("F8 当日委托 OCR 读取失败")
        entrust_rows = list(entrust_rows)
    except Exception as exc:
        entrust_rows = None
        entrust_error = sanitize_sensitive_text(exc)
    else:
        entrust_error = ""
    for result in pending:
        verified = None if entrust_rows is None else any(_matches_entrust(row, result) for row in entrust_rows)
        if verified:
            result.update(status="submitted", reason="", error_code="", error="",
                          verified=True, client_return=message)
        else:
            if entrust_rows is None:
                code = "IPO_ENTRUST_UNVERIFIED"
                reason = "F8 查询失败，提交结果未核验"
                error = f"{reason}：{entrust_error}"
            else:
                code = "IPO_ENTRUST_NOT_FOUND"
                reason = "提交后 F8 当日委托未确认"
                error = reason
            result.update(status="submitted_unverified", reason=reason, error_code=code,
                          error=error, verified=verified, client_return=message)
        if ledger is not None:
            try:
                ledger.mark(account_id, result, result["status"], account_key=account_key,
                            client_id=client_id, reason=result["reason"],
                            error_code=result["error_code"], error=result["error"],
                            verified=result["verified"])
            except Exception as exc:
                result["error_code"] = "ORDER_LEDGER_WRITE_FAILED"
                result["error"] = sanitize_sensitive_text(exc)
    return results