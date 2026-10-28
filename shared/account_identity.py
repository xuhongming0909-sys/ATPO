# AI-SUMMARY: 统一资金账户身份字段与账户明细去重——显示层全量（完整资金账号/显示名/THS 用户名），内部去重键不变
from collections.abc import Mapping
from typing import Any


def _first(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _tail4(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[-4:] if len(digits) >= 4 else ""


def account_identity(ths_username: str = "", row: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """把不同执行模块的账户行统一成推送和去重需要的身份字段；全部原样显示。"""
    row = row if isinstance(row, Mapping) else {}
    display_name = _first(row, "display_text", "display_name", "account", "observed_display_masked")
    fund_account = _first(row, "fund_account", "current_fund_account", "observed_current",
                          "observed_current_masked")
    ths_account = _first(row, "ths_account", "username") or str(ths_username or "")
    explicit_key = _first(row, "account_key", "fund_account_hash", "target_key", "key")
    if not explicit_key and fund_account:
        explicit_key = fund_account
    if not explicit_key:
        suffix = fund_account or ths_account
        explicit_key = f"{display_name}|{suffix}" if display_name or suffix else f"row|{row.get('index', '')}"
    return {
        "account_key": explicit_key,
        "account": display_name or ths_account,
        "display_name": display_name or ths_account,
        "ths_account": ths_account,
        "fund_account": fund_account,
        "fund_account_masked": _first(row, "fund_account_masked") or fund_account,
        "fund_account_tail4": _first(row, "fund_account_tail4") or _tail4(fund_account),
        "observed_current_account": _first(row, "observed_current", "observed_current_masked"),
    }


def unique_account_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 account_key 去重；同一账户出现成功和失败时保留成功记录。"""
    def rank(item: dict[str, Any]) -> int:
        status = str(item.get("login_status") or item.get("status") or "").lower()
        return 2 if status in {"ready", "already_logged_in", "success", "logged_in"} else 1

    selected: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        row = dict(item)
        key = str(row.get("account_key") or account_identity(row.get("ths_account", ""), row)["account_key"])
        row.setdefault("account_key", key)
        if key not in selected:
            selected[key] = row
            order.append(key)
        elif rank(row) > rank(selected[key]):
            selected[key] = row
    return [selected[key] for key in order]
