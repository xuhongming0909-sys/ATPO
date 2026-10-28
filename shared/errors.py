# AI-SUMMARY: 统一业务错误——错误码、用户消息、修复提示和凭据脱敏输出（仅密码/验证码/SendKey/token，账户信息完整保留）
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
from typing import Any

from shared.paths import ensure_runtime_dirs, runtime_path


_URL = re.compile(
    r"(?i)(?:\b[a-z][a-z0-9+.-]*://[^\s<>{}\[\]\"']+|\bwww\.[^\s<>{}\[\]\"']+"
    r"|\b[a-z0-9.-]*sctapi\.ftqq\.com[^\s<>{}\[\]\"']*)"
)
_SENDKEY = re.compile(r"(?i)\bSCT[A-Za-z0-9_-]{8,}\b")
# 仅凭据类关键词脱敏；账户识别信息（资金账号/显示名/THS 用户名）按用户要求完整保留
_CREDENTIAL_NAME = r"password|passwd|pwd|密码|captcha|验证码|sendkey|secret|token"
_SENSITIVE_ASSIGN = re.compile(
    rf"(?P<key>[\"']?(?:{_CREDENTIAL_NAME})[\"']?)(?P<sep>\s*[:=：]\s*)"
    rf"(?P<value>.*?)(?=(?:\s*[\"']?(?:{_CREDENTIAL_NAME})[\"']?\s*[:=：])|[\r\n]|$)",
    re.I | re.S,
)
_SENSITIVE_KEY = re.compile(rf"^(?:{_CREDENTIAL_NAME})$", re.I)
_URL_KEYS = {"url", "uri", "link", "endpoint"}


def sanitize_sensitive_text(value: object) -> str:
    """移敏文本：URL、SendKey、凭据赋值值移除；账户信息完整保留。"""
    text = _URL.sub("***URL***", str(value))
    text = _SENDKEY.sub("***", text)

    def _assign(match: re.Match[str]) -> str:
        return f"{match.group('key')}{match.group('sep')}***"

    text = _SENSITIVE_ASSIGN.sub(_assign, text)
    return re.sub(r"(验证码|captcha)\s*[:=：]?\s*\d{4,8}", r"\1***", text, flags=re.I)


def sanitize_sensitive_value(value: Any) -> Any:
    """递归移敏任意错误上下文；凭据键的值直接替换，其他内容原样保留。"""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            name = str(key)
            if _SENSITIVE_KEY.match(name):
                result[sanitize_sensitive_text(name)] = "***"
            elif name.lower() in _URL_KEYS:
                result[sanitize_sensitive_text(name)] = "***URL***"
            else:
                result[sanitize_sensitive_text(name)] = sanitize_sensitive_value(item)
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize_sensitive_value(item) for item in value]
    if isinstance(value, Path):
        return sanitize_sensitive_text(str(value))
    if isinstance(value, str):
        return sanitize_sensitive_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_sensitive_text(value)


def _safe(value: object) -> str:
    return sanitize_sensitive_text(value)


@dataclass
class AutoIpoError(RuntimeError):
    code: str
    message: str
    hint: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{_safe(self.code)}] {_safe(self.message)}"

    def as_dict(self) -> dict:
        context = sanitize_sensitive_value(self.context)
        hint = sanitize_sensitive_text(self.hint)
        return {
            "code": sanitize_sensitive_text(self.code),
            "message": sanitize_sensitive_text(self.message),
            "hint": hint,
            "next_action": hint,
            "path": sanitize_sensitive_text(self.context.get("path", "")),
            "context": context,
        }


def format_error(exc: Exception) -> str:
    if isinstance(exc, AutoIpoError):
        lines = [f"[{_safe(exc.code)}] {_safe(exc.message)}"]
        if exc.context:
            lines.append("位置: " + ", ".join(
                f"{k}={sanitize_sensitive_value(v)}" for k, v in exc.context.items()
            ))
        if exc.hint:
            lines.append("修复/下一步: " + _safe(exc.hint))
        return "\n".join(lines)
    return f"[UNEXPECTED_ERROR] {type(exc).__name__}: {_safe(exc)}"


def save_error_report(exc: Exception, command: str = "") -> Path:
    ensure_runtime_dirs()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = runtime_path("errors", f"{stamp}_{_safe(command) or 'unknown'}.txt")
    payload = exc.as_dict() if isinstance(exc, AutoIpoError) else {
        "code": "UNEXPECTED_ERROR",
        "message": f"{type(exc).__name__}: {_safe(exc)}",
        "hint": "查看 traceback 后运行 python run.py doctor",
        "next_action": "查看 traceback 后运行 python run.py doctor",
        "path": "",
        "context": {"command": _safe(command)},
    }
    lines = [f"time={datetime.now().isoformat(timespec='seconds')}", f"command={_safe(command)}"]
    lines.extend(f"{k}={sanitize_sensitive_value(v)}" for k, v in payload.items())
    if not isinstance(exc, AutoIpoError):
        import traceback
        lines.append("traceback=" + _safe(traceback.format_exc()))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path

