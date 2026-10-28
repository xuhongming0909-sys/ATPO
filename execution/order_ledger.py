# AI-SUMMARY: 每日实盘订单台账——缺失才初始化，损坏/未知版本/写入失败全部 fail-closed
import json
from datetime import datetime
from pathlib import Path

from shared.errors import AutoIpoError, sanitize_sensitive_text, sanitize_sensitive_value
from shared.paths import runtime_path

LEDGER_VERSION = 2
KNOWN_VERSIONS = {1, LEDGER_VERSION}
DEFAULT_ROOT = runtime_path("order_ledger")
_DROP_KEYS = {"fund_account", "资金账号", "资金帐号", "password", "password_enc", "密码", "captcha", "验证码", "sendkey", "secret", "token"}


class OrderLedger:
    def __init__(self, day: str, root: Path | None = None, *, allow_repeat: bool = False):
        self.day = day
        self.allow_repeat = bool(allow_repeat)
        self.path = (root or DEFAULT_ROOT) / f"{day}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_failed = False
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            data = {"version": LEDGER_VERSION, "day": self.day, "orders": {}}
            self._write(data, initial=True)
            return data
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise AutoIpoError(
                "ORDER_LEDGER_CORRUPT",
                "订单台账文件损坏，已拒绝读取并保留原文件",
                "请人工检查 runtime_data/order_ledger 后再运行 live",
                {"path": self.path, "detail": sanitize_sensitive_text(exc)},
            ) from None
        if not isinstance(raw, dict):
            raise AutoIpoError(
                "ORDER_LEDGER_CORRUPT",
                "订单台账结构损坏，已拒绝读取并保留原文件",
                "请人工检查 runtime_data/order_ledger 后再运行 live",
                {"path": self.path},
            )
        if raw.get("version") not in KNOWN_VERSIONS:
            raise AutoIpoError(
                "ORDER_LEDGER_VERSION_UNKNOWN",
                "订单台账版本未知，已拒绝读取并保留原文件",
                "请升级程序或人工确认台账版本后再运行 live",
                {"path": self.path, "version": raw.get("version")},
            )
        if not isinstance(raw.get("orders"), dict):
            raise AutoIpoError(
                "ORDER_LEDGER_CORRUPT",
                "订单台账结构损坏，已拒绝读取并保留原文件",
                "请人工检查 runtime_data/order_ledger 后再运行 live",
                {"path": self.path},
            )
        return raw

    def _write(self, data: dict, initial: bool = False) -> None:
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
            tmp.replace(self.path)
        except Exception as exc:
            self._write_failed = True
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            code = "ORDER_LEDGER_WRITE_FAILED"
            message = "订单台账写入失败，已阻断后续 live begin"
            if initial:
                message = "订单台账初始化写入失败，已阻断 live begin"
            raise AutoIpoError(
                code,
                message,
                "请检查磁盘/权限后重试；不要删除已有台账文件",
                {"path": self.path, "detail": sanitize_sensitive_text(exc)},
            ) from None

    def _save(self) -> None:
        if self._write_failed:
            raise AutoIpoError(
                "ORDER_LEDGER_WRITE_FAILED",
                "订单台账已处于写入失败状态，已阻断后续 live begin",
                "请先修复磁盘/权限并人工确认台账内容",
                {"path": self.path},
            )
        self.data["version"] = LEDGER_VERSION
        self._write(self.data)

    @staticmethod
    def _identity(account_id: str, account_key: str | None) -> str:
        return str(account_key or account_id)

    @classmethod
    def _key(cls, account_id: str, apply_code: str, account_key: str | None = None) -> str:
        return f"{cls._identity(account_id, account_key)}|{apply_code}"

    @staticmethod
    def _clean_extra(extra: dict) -> dict:
        clean = {}
        for key, value in (extra or {}).items():
            if str(key).lower() in _DROP_KEYS:
                continue
            clean[str(key)] = sanitize_sensitive_value(value)
        return clean

    def begin(self, account_id: str, order: dict, *, account_key: str | None = None,
              client_id: str = "") -> bool:
        if self._write_failed:
            self._save()
        code = str(order.get("apply_code", ""))
        key = self._key(account_id, code, account_key)
        if key in self.data["orders"] and not self.allow_repeat:
            return False
        current = self.data["orders"].get(key)
        attempt_count = int((current or {}).get("attempt_count", 1)) + (1 if current else 0)
        self.data["orders"][key] = {
            "account_id": sanitize_sensitive_text(account_id),
            "account_key": self._identity(account_id, account_key),
            "client_id": client_id,
            "apply_code": code,
            "name": sanitize_sensitive_text(order.get("name", "")),
            "status": "unknown",
            "reason": "已发起，结果待确认",
            "error_code": "ORDER_RESULT_UNCONFIRMED",
            "error": "已发起，结果待确认",
            "verified": None,
            "attempt_count": attempt_count,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._save()
        return True

    def mark(self, account_id: str, order: dict, status: str, *, account_key: str | None = None,
             client_id: str = "", **extra) -> dict:
        if self._write_failed:
            self._save()
        code = str(order.get("apply_code", ""))
        key = self._key(account_id, code, account_key)
        row = self.data["orders"].setdefault(key, {
            "account_id": sanitize_sensitive_text(account_id),
            "account_key": self._identity(account_id, account_key),
            "client_id": client_id,
            "apply_code": code,
            "name": sanitize_sensitive_text(order.get("name", "")),
            "verified": None,
        })
        row.update(status=status, updated_at=datetime.now().isoformat(timespec="seconds"))
        if client_id:
            row["client_id"] = client_id
        clean_extra = self._clean_extra(extra)
        row.update(clean_extra)
        row.setdefault("reason", "")
        row.setdefault("error_code", "")
        row.setdefault("error", "")
        self._save()
        return row

    def get(self, account_id: str, apply_code: str, *, account_key: str | None = None) -> dict | None:
        return self.data["orders"].get(self._key(account_id, apply_code, account_key))