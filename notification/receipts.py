# AI-SUMMARY: 登录/申购/中签标准回执——时间+账户+事件全量渲染（仅排除密码/验证码/SendKey 等凭据）与开关化 Server酱发送
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from notification import serverchan
from shared.config import load_config

_KINDS = {"login", "subscribe", "allotment"}
_SWITCHES = {"login": "send_login", "subscribe": "send_subscribe", "allotment": "send_allotment"}
from shared.account_identity import account_identity, unique_account_items

_CREDENTIAL_KEY = re.compile(r"(password|passwd|pwd|密码|captcha|验证码|sendkey|secret|token)", re.I)
_CREDENTIAL_ASSIGN = re.compile(
    r"(password|passwd|pwd|密码|captcha|验证码|sendkey|secret|token)"
    r"(\s*[:=：]\s*)[^\s｜|，,;；]+",
    re.I,
)


def _safe_text(value: Any, default: str = "—") -> str:
    """凭据赋值脱敏；账户识别信息（资金账号等数字）完整保留。"""
    if value is None:
        return default
    text = _CREDENTIAL_ASSIGN.sub(r"\1\2***", str(value))
    text = re.sub(r"(验证码|captcha)\s*[:=：]?\s*\d{4,8}", r"\1***", text, flags=re.I)
    return " ".join(text.split()) or default


def _mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        return {}
    return {key: value for key, value in data.items() if not _CREDENTIAL_KEY.search(str(key))}


def _list(data: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key)
    if not isinstance(value, list):
        return []
    return [_mapping(item) for item in value if isinstance(item, Mapping)]


def _number(data: Mapping[str, Any], key: str, default: int = 0) -> int:
    value = data.get(key)
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _date(data: Mapping[str, Any]) -> tuple[str, str]:
    raw = _safe_text(data.get("date"), "")
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw)
    return raw or "未提供", f"{int(match.group(2))}/{int(match.group(3))}" if match else raw or "/"


def _time_label(data: Mapping[str, Any], now: datetime | None = None) -> str:
    """回执时间：优先 data.time（HH:MM），否则取当前时间。"""
    raw = str(data.get("time") or "").strip()
    if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?", raw):
        return raw[:5]
    return (now or datetime.now()).strftime("%H:%M")


def _item_time(item: Mapping[str, Any], fallback: str) -> str:
    raw = str(item.get("time") or item.get("成交时间") or item.get("委托时间") or "").strip()
    match = re.search(r"([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?", raw)
    return match.group(0)[:5] if match else fallback


def _next_action(data: Mapping[str, Any]) -> str:
    return _safe_text(data.get("next_action"), "")


_LOGIN_SUCCESS = {"ready", "already_logged_in", "success", "logged_in"}


def _login_status(account: Mapping[str, Any]) -> str:
    return str(account.get("login_status") or account.get("status") or "").lower()


_LOGIN_MANUAL = {"dialog_required", "dialog_closed", "manual_required", "login_required"}


def _login_category(account: Mapping[str, Any]) -> str:
    status = _login_status(account)
    if account.get("manual_required") or status in _LOGIN_MANUAL:
        return "manual"
    return "success" if status in _LOGIN_SUCCESS else "failed"


def _login_rows(clients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for client in clients:
        client_name = str(client.get("ths_account") or client.get("id") or client.get("client_id") or "")
        for account in _list(client, "accounts"):
            identity = account_identity(client_name, account)
            rows.append({**account, **identity, "_client_name": client_name})
    return unique_account_items(rows)


def _login_counts(clients: list[dict[str, Any]]) -> dict[str, int]:
    rows = _login_rows(clients)
    categories = [_login_category(account) for account in rows]
    return {
        "total": len(rows),
        "success": categories.count("success"),
        "manual": categories.count("manual"),
        "failed": categories.count("failed"),
    }


def _identity_parts(account: Mapping[str, Any]) -> list[str]:
    """账户行：显示名 + 资金账号（完整）+ THS 登录账户，全部原样显示。"""
    parts = [f"账户：{_safe_text(account.get('display_name') or account.get('account'), '—')}"]
    fund_account = str(account.get("fund_account") or "").strip()
    if fund_account:
        parts.append(f"资金账号：{fund_account}")
    ths_account = str(account.get("ths_account") or account.get("_client_name") or "").strip()
    if ths_account:
        parts.append(f"THS：{ths_account}")
    return parts


def _login_detail(account: Mapping[str, Any], category: str) -> str:
    detail = _safe_text(account.get("detail") or account.get("error"), "")
    status = _login_status(account)
    if detail and detail != "—":
        return detail
    if category == "manual":
        return "资金账户登录弹窗已关闭，需人工处理" if status == "dialog_closed" else "需填写资金账号/密码/验证码"
    return status or "failed"


def _render_login(data: dict[str, Any], now: datetime | None) -> tuple[str, str]:
    date_text, date_label = _date(data)
    time_label = _time_label(data, now)
    clients = _list(data, "clients") or [{"accounts": _list(data, "items")}]
    counts = _login_counts(clients)
    title = (f"[登录回执][{date_label} {time_label}] 成功 {counts['success']}｜"
             f"需人工 {counts['manual']}｜失败 {counts['failed']}")
    lines = [f"日期：{date_text}", f"时间：{(now or datetime.now()).strftime('%Y-%m-%d %H:%M:%S')}"]
    if _number(data, "total"):
        lines.append(f"结果：共 {counts['total']} 户")
    for account in _login_rows(clients):
        category = _login_category(account)
        label = {"success": "登录成功", "manual": "需人工处理", "failed": "登录失败"}[category]
        detail = _login_detail(account, category)
        status = _login_status(account)
        parts = _identity_parts(account) + [f"事件：{label}"]
        if status:
            parts.append(f"状态码：{status}")
        if detail and detail != "—":
            parts.append(f"原因：{detail}")
        lines.append("- " + "｜".join(parts))
    lines.append(f"下一步：{_next_action(data) or '失败账户按状态和原因人工核对。'}")
    return title, "\n".join(lines)


def _render_subscribe(data: dict[str, Any], now: datetime | None) -> tuple[str, str]:
    date_text, date_label = _date(data)
    time_label = _time_label(data, now)
    items = _list(data, "items")
    success_statuses = {"submitted", "success", "ok"}
    skipped_statuses = {"skipped", "duplicate_account", "dry_run", "expired"}
    counts = {"success": 0, "skipped": 0, "failed": 0}
    for item in items:
        status = str(item.get("status", "")).lower()
        if status in success_statuses:
            counts["success"] += 1
        elif status in skipped_statuses:
            counts["skipped"] += 1
        else:
            counts["failed"] += 1
    summary = _mapping(data.get("summary") or {})
    for key, target in (("success", "success"), ("skipped", "skipped"), ("failed", "failed")):
        if _number(summary, key):
            counts[target] = _number(summary, key)
    title = (f"[申购回执][{date_label} {time_label}] 成功 {counts['success']}｜"
             f"跳过 {counts['skipped']}｜失败 {counts['failed']}")
    lines = [f"日期：{date_text}", f"时间：{(now or datetime.now()).strftime('%Y-%m-%d %H:%M:%S')}"]
    for item in items:
        code = _safe_text(item.get("apply_code"), "")
        name = _safe_text(item.get("name"))
        target = f"{name}（{code}）" if code and code != "—" else name
        amount = _safe_text(item.get("amount"), "")
        unit = _safe_text(item.get("unit"), "")
        quantity = " ".join(x for x in (amount, unit) if x and x != "—")
        reason = _safe_text(item.get("reason"), "")
        reason_label = "原因" if not reason or reason == "—" else "失败原因"
        reason = "无" if not reason or reason == "—" else reason
        stamp = _item_time(item, time_label)
        lines.append(f"- [{stamp}] " + "｜".join(_identity_parts(item)) +
                     f"｜申购：{target}｜数量：{quantity or '—'}｜"
                     f"状态：{_safe_text(item.get('status'))}｜{reason_label}：{reason}")
    action = _next_action(data) or "失败或不确定项人工核对当日委托，禁止重复提交。"
    lines.append(f"下一步：{action}")
    return title, "\n".join(lines)


def _is_won(item: dict[str, Any]) -> bool:
    status = str(item.get("status", "")).lower()
    qty = item.get("winning_qty", item.get("qty"))
    return status in {"won", "win", "success", "中签"} or (
        isinstance(qty, (int, float)) and not isinstance(qty, bool) and qty > 0
    )


def _allotment_counts(data: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, int]:
    accounts = {_safe_text(item.get("account")) for item in items if _is_won(item)}
    return {
        "winning_accounts": len(accounts),
        "winning_records": sum(_is_won(item) for item in items),
    }


def _render_allotment(data: dict[str, Any], now: datetime | None) -> tuple[str, str]:
    date_text, date_label = _date(data)
    time_label = _time_label(data, now)
    items = _list(data, "items")
    counts = _allotment_counts(data, items)
    won = counts["winning_accounts"] > 0
    title = f"[中签回执][{date_label} {time_label}] 中签 {counts['winning_accounts']} 户" if won else f"[中签回执][{date_label} {time_label}] 无中签"
    lines = [f"日期：{date_text}", f"时间：{(now or datetime.now()).strftime('%Y-%m-%d %H:%M:%S')}",
             f"结果：中签 {counts['winning_accounts']} 户"]
    for item in items:
        code = _safe_text(item.get("apply_code"), "")
        name = _safe_text(item.get("name"))
        target = f"{name}（{code}）" if code and code != "—" else name
        qty = _safe_text(item.get("winning_qty", item.get("qty")), "—")
        payment = _safe_text(item.get("payment_amount", item.get("payment")), "—")
        reason = _safe_text(item.get("reason"), "")
        suffix = f"｜原因：{reason}" if reason and reason != "—" else ""
        stamp = _item_time(item, time_label)
        lines.append(f"- [{stamp}] " + "｜".join(_identity_parts(item)) + f"｜中签：{target}｜"
                     f"中签数量：{qty}｜缴款金额：{payment} 元｜状态：{_safe_text(item.get('status'))}{suffix}")
    unpublished = any(str(item.get("status", "")).lower() in
                      {"unpublished", "not_published", "data_unavailable", "pending"} for item in items)
    unpublished = unpublished or bool(_mapping(data.get("summary") or {}).get("data_unpublished"))
    if not won:
        lines.append("数据未公布，将继续补查" if unpublished else "无中签")
    if won:
        lines.append("缴款提醒：中签账户请在缴款截止时间前确保可用资金足额。")
    action = _next_action(data) or ("中签账户请在缴款截止时间前确保可用资金足额。" if won else
                                    "数据未公布，将继续补查。" if unpublished else "无需处理。")
    lines.append(f"下一步：{action}")
    return title, "\n".join(lines)


def render_receipt(kind: str, data: Mapping[str, Any], *, now: datetime | None = None) -> tuple[str, str]:
    """纯函数渲染标准化回执；不读取配置、不发送、不记录敏感字段。"""
    if kind not in _KINDS:
        raise ValueError(f"kind 仅支持 login/subscribe/allotment，收到：{kind}")
    if not isinstance(data, Mapping):
        raise TypeError("data 必须是 Mapping")
    safe = _mapping(data)
    renderers = {"login": _render_login, "subscribe": _render_subscribe, "allotment": _render_allotment}
    return renderers[kind](safe, now)


def send_receipt(kind: str, data: Mapping[str, Any], *,
                 config: Mapping[str, Any] | None = None, sender=None) -> dict:
    """按 notification_receipts 开关发送标准化回执；config/sender 可注入，开关关闭时不联网。"""
    if kind not in _SWITCHES:
        raise ValueError(f"kind 仅支持 login/subscribe/allotment，收到：{kind}")
    cfg = (config if config is not None else load_config()).get("notification_receipts", {})
    version = cfg.get("template_version", 2)
    if version != 2:
        raise ValueError(f"不支持的 notification_receipts.template_version: {version}")
    if not cfg.get(_SWITCHES[kind], False):
        return {"kind": kind, "sent": False, "reason": "disabled"}
    title, body = render_receipt(kind, data)
    result = (sender or serverchan.send)(title, body)
    return {"kind": kind, "sent": True, "title": title, "body": body, "result": result}

