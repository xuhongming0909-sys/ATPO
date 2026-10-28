# AI-SUMMARY: 统一账户会话结果、资金账号哈希与脱敏工具——运行时状态不保存完整资金账号
from dataclasses import asdict, dataclass, replace
from hashlib import sha256

STATUS_READY = "ready"
STATUS_ALREADY_LOGGED_IN = "already_logged_in"
STATUS_LOGIN_REQUIRED = "login_required"
STATUS_DIALOG_CLOSED = "dialog_closed"
STATUS_WRONG_ACCOUNT = "wrong_account"
STATUS_NOT_LOGGED_IN = "not_logged_in"
STATUS_DIALOG_REQUIRED = "dialog_required"
STATUS_MENU_FAILED = "menu_failed"
STATUS_XIADAN_FAILED = "xiadan_failed"
STATUS_NOT_SELECTED = "not_selected"
STATUS_CONFIG_MISSING = "config_missing"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_DUPLICATE_ACCOUNT = "duplicate_account"
STATUS_CLIENT_FAILED = "client_failed"

KNOWN_STATUSES = {
    STATUS_READY,
    STATUS_ALREADY_LOGGED_IN,
    STATUS_LOGIN_REQUIRED,
    STATUS_DIALOG_CLOSED,
    STATUS_WRONG_ACCOUNT,
    STATUS_NOT_LOGGED_IN,
    STATUS_DIALOG_REQUIRED,
    STATUS_MENU_FAILED,
    STATUS_XIADAN_FAILED,
    STATUS_NOT_SELECTED,
    STATUS_CONFIG_MISSING,
    STATUS_AMBIGUOUS,
    STATUS_DUPLICATE_ACCOUNT,
    STATUS_CLIENT_FAILED,
}


@dataclass
class AccountSessionResult:
    account_id: str
    display_name: str = ""
    fund_account_hash: str = ""
    main_menu_row: int | None = None
    xiadan_present: bool = False
    current_fund_account: str = ""
    status: str = STATUS_NOT_LOGGED_IN
    error: str = ""
    client_id: str = ""

    def as_dict(self) -> dict:
        return asdict(self)

    def with_updates(self, **updates) -> "AccountSessionResult":
        return replace(self, **updates)


def hash_fund_account(fund_account: str) -> str:
    return sha256((fund_account or "").encode("utf-8")).hexdigest()


def mask_fund_account(fund_account: str) -> str:
    value = fund_account or ""
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}****{value[-4:]}"


def session_from_mapping(value: "AccountSessionResult | dict | str", account_id: str) -> AccountSessionResult:
    if isinstance(value, AccountSessionResult):
        return value
    if isinstance(value, str):
        return AccountSessionResult(
            account_id=account_id,
            display_name=value or account_id,
            status=STATUS_READY,
            xiadan_present=True,
        )
    data = dict(value or {})
    data.setdefault("account_id", account_id)
    return AccountSessionResult(**{k: v for k, v in data.items() if k in AccountSessionResult.__annotations__})
