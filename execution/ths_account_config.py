# AI-SUMMARY: 单客户端多同花顺登录账户配置——客户端显示名、10 户上限、路径和 DPAPI 密码读取
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shared.config import load_secrets
from shared.credstore import decrypt_text
from shared.errors import AutoIpoError
from shared.paths import resolve_path


@dataclass(frozen=True)
class ThsLoginAccount:
    username: str
    enabled: bool = True


@dataclass(frozen=True)
class ThsAccountModeConfig:
    hexin_path: Path
    xiadan_path: Path
    accounts: tuple[ThsLoginAccount, ...]
    max_ths_accounts: int = 10
    max_fund_accounts_per_ths: int = 10


def _mode_mapping(cfg: dict) -> dict:
    mode = (cfg.get("execution") or {}).get("ths_account_switch")
    if not isinstance(mode, dict):
        raise AutoIpoError(
            "THS_MODE_CONFIG_MISSING",
            "缺少 execution.ths_account_switch 配置",
            "从 config/config.example.yaml 复制 ths_account_switch 段",
        )
    return mode


def _account_limit(value: object, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
        raise AutoIpoError(
            "THS_ACCOUNT_LIMIT_INVALID",
            f"{key} 必须是 1 到 10 的整数",
            "修改 execution.ths_account_switch 的账户数量上限",
            {"key": key, "value": value},
        )
    return value


def load_ths_account_mode(cfg: dict) -> ThsAccountModeConfig:
    mode = _mode_mapping(cfg)
    raw_accounts = mode.get("accounts")
    if not isinstance(raw_accounts, list) or not raw_accounts:
        raise AutoIpoError(
            "THS_ACCOUNTS_MISSING",
            "ths_account_switch.accounts 必须是非空列表",
            "按客户端显示名配置 1 至 10 个同花顺账户",
        )
    if len(raw_accounts) > 10:
        raise AutoIpoError(
            "THS_ACCOUNT_LIMIT",
            "同花顺登录账户最多配置 10 个",
            "减少 ths_account_switch.accounts 后重试",
            {"count": len(raw_accounts)},
        )
    accounts: list[ThsLoginAccount] = []
    seen: set[str] = set()
    for row in raw_accounts:
        if not isinstance(row, dict):
            raise AutoIpoError(
                "THS_ACCOUNT_INVALID",
                "同花顺账户项必须包含 username",
                "每项格式：{username: 客户端显示名, enabled: true}",
            )
        username = str(row.get("username") or "").strip()
        if not username:
            raise AutoIpoError(
                "THS_ACCOUNT_INVALID",
                "同花顺账户 username 不能为空",
                "使用客户端账号下拉中的显示名",
            )
        if username in seen:
            raise AutoIpoError(
                "THS_ACCOUNT_DUPLICATE",
                f"同花顺账户显示名重复：{username}",
                "每个客户端显示名只能配置一次",
                {"username": username},
            )
        seen.add(username)
        accounts.append(ThsLoginAccount(username=username, enabled=bool(row.get("enabled", True))))
    hexin_path = resolve_path(mode.get("hexin_path", ""))
    xiadan_path = resolve_path(mode.get("xiadan_path", ""))
    if not mode.get("hexin_path") or not mode.get("xiadan_path"):
        raise AutoIpoError(
            "THS_MODE_PATH_INVALID",
            "同花顺 hexin_path/xiadan_path 不能为空",
            "修改 execution.ths_account_switch 的两个 exe 绝对路径",
            {"hexin_path": str(hexin_path), "xiadan_path": str(xiadan_path)},
        )
    max_ths_accounts = _account_limit(mode.get("max_ths_accounts", 10), "max_ths_accounts")
    max_fund_accounts = _account_limit(
        mode.get("max_fund_accounts_per_ths", 10), "max_fund_accounts_per_ths"
    )
    return ThsAccountModeConfig(
        hexin_path=hexin_path,
        xiadan_path=xiadan_path,
        accounts=tuple(accounts),
        max_ths_accounts=max_ths_accounts,
        max_fund_accounts_per_ths=max_fund_accounts,
    )


def read_ths_password(username: str) -> str:
    entry = (load_secrets().get("ths_account_secrets") or {}).get(username) or {}
    token = entry.get("password_enc")
    if not token:
        raise AutoIpoError(
            "THS_PASSWORD_MISSING",
            f"同花顺账户 {username} 缺少 DPAPI 密码密文",
            "重新录入该账户登录密码；明文不得写入配置",
            {"username": username},
        )
    try:
        return decrypt_text(str(token))
    except Exception as exc:
        raise AutoIpoError(
            "THS_PASSWORD_DECRYPT_FAILED",
            f"同花顺账户 {username} 密码密文无法解密",
            "换电脑/Windows 用户后必须重新录入密码",
            {"username": username, "error": "DPAPI_DECRYPT_FAILED"},
        ) from exc
