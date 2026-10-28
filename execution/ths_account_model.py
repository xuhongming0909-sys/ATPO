# AI-SUMMARY: 同花顺资金账户标签解析、脱敏标识和唯一匹配模型
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from execution.account_session import hash_fund_account, mask_fund_account
from shared.errors import AutoIpoError, sanitize_sensitive_text

_FULL_ACCOUNT = re.compile(r"\d{6,32}")
_TAIL4 = re.compile(r"(?<!\d)(?:\*{0,28})?(\d{4})(?!\d)")
_MASKED_ACCOUNT = re.compile(r"(?<!\d)(?:\d[\doil]{0,7})?\*{2,}(?:\d[\doil]{0,7})?(?!\d)", re.I)
_USERNAME_TOKEN = re.compile(r"(?<![A-Za-z0-9_])mx_[A-Za-z0-9]{4,16}(?![A-Za-z0-9_])", re.I)
_MASKED_FUZZY_MIN_RATIO = 0.88
_MASKED_FUZZY_MIN_GAP = 0.10

def _safe(value: object) -> str:
    return sanitize_sensitive_text(value)

def _norm(value: object) -> str:
    return "".join(str(value or "").split()).replace("－", "-").lower()

def _clean_account_label(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^[\s\W_]+", "", text, flags=re.UNICODE)
    text = re.sub(r"F12\s*已登录|已登录|F12|委托交易", " ", text, flags=re.I)
    return " ".join(text.split())

def _tail4(value: object) -> str:
    matches = _TAIL4.findall(str(value or ""))
    return matches[-1] if matches else ""

def _masked_from_label(value: object) -> str:
    def mask(match: re.Match[str]) -> str:
        return mask_fund_account(match.group(0))

    return re.sub(r"\d{6,32}", mask, str(value or ""))

def _masked_match_text(value: object) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff*]+", "", _norm(value)).replace("o", "0")


def _display_identity_key(value: object) -> str:
    text = _clean_account_label(value)
    text = re.sub(r"^国\s+", "", text)
    text = re.sub(r"(证券)[一－—](?=[\u4e00-\u9fff*])", r"\1-", text)
    return _norm(text)

def _masked_account_text(value: object) -> str:
    matches = _MASKED_ACCOUNT.findall(_norm(value))
    return _masked_match_text(matches[-1]) if matches else ""

def _row_identity_tail(value: object) -> str:
    parts = [part for part in re.split(r"[-－—]", str(value or "")) if part.strip()]
    return _masked_match_text(parts[-1]) if parts else ""

def _masked_account_parts(value: object) -> tuple[str, str]:
    match = _MASKED_ACCOUNT.search(_norm(value))
    if not match:
        return "", ""
    token = re.sub(r"[Oo]", "0", match.group(0))
    token = re.sub(r"[Il]", "1", token)
    parts = re.split(r"\*{2,}", token)
    if len(parts) != 2:
        return "", ""
    prefix = re.sub(r"\D", "", parts[0])
    tail = re.sub(r"\D", "", parts[1])[-4:]
    return prefix, tail

def _observed_masked(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    digits = re.sub(r"\D", "", text)
    if digits and _FULL_ACCOUNT.fullmatch(digits):
        return f"****{digits[-4:]}"
    return _masked_from_label(text)

def _menu_row_kind(value: object) -> str:
    text = _clean_account_label(value)
    if _masked_account_text(text):
        return "login_required"
    tail = _row_identity_tail(text)
    if tail and "*" in tail and re.search(r"[\u4e00-\u9fff]", tail):
        return "direct"
    if re.search(r"(?:证券|期货)$", text) and "-" not in text:
        return "login_required"
    return "direct" if _FULL_ACCOUNT.search(text) else "unknown"

def _masked_fuzzy_match(
    options: Sequence["FundAccountRef"],
    target: str,
) -> tuple["FundAccountRef | None", str]:
    wanted = _masked_match_text(target)
    wanted_account = _masked_account_text(target)
    wanted_tail = _row_identity_tail(target)
    if len(wanted) < 6 and not wanted_account and not wanted_tail:
        return None, "FUND_ACCOUNT_NOT_FOUND"
    if wanted_account:
        account_matches = [
            item for item in options
            if wanted_account in {
                _masked_account_text(item.display_masked),
                _masked_account_text(item.fund_account_masked),
                _masked_account_text(item._display_text),
            }
        ]
        return _unique_or_error(account_matches)
    scored = []
    for item in options:
        candidates_text = (
            _masked_match_text(item.display_masked),
            _masked_match_text(item.fund_account_masked),
            _masked_match_text(item._display_text),
        )
        tail_score = max(
            SequenceMatcher(None, wanted_tail, _row_identity_tail(candidate)).ratio()
            for candidate in candidates_text
        ) if wanted_tail else 0.0
        candidates = (
            _masked_match_text(item.display_masked),
            _masked_match_text(item.fund_account_masked),
        )
        text_score = max(
            SequenceMatcher(None, wanted, candidate).ratio()
            for candidate in candidates
        )
        scored.append((max(tail_score, text_score), item, tail_score))
    scored.sort(key=lambda row: row[0], reverse=True)
    if not scored or scored[0][0] < _MASKED_FUZZY_MIN_RATIO:
        if scored and wanted_tail and scored[0][2] >= 0.82:
            if len(scored) == 1 or scored[0][0] - scored[1][0] >= _MASKED_FUZZY_MIN_GAP:
                return scored[0][1], ""
        return None, "FUND_ACCOUNT_NOT_FOUND"
    if len(scored) > 1 and scored[0][0] - scored[1][0] < _MASKED_FUZZY_MIN_GAP:
        return None, "FUND_ACCOUNT_AMBIGUOUS"
    return scored[0][1], ""

def match_fund_account(
    options: Sequence[FundAccountRef],
    target: FundAccountRef | Mapping[str, Any] | str,
    *,
    allow_fuzzy: bool = True,
) -> tuple[FundAccountRef | None, str]:
    """完整账号哈希优先；无哈希 OCR 行只按脱敏文本高相似度且明显领先唯一匹配。"""
    if isinstance(target, FundAccountRef):
        target = target.safe_dict()
    elif isinstance(target, str):
        target = {"display_text": target}
    data = dict(target or {})
    raw_account = str(data.get("fund_account") or "")
    target_hash = str(data.get("fund_account_hash") or "")
    text = str(data.get("display_text") or data.get("display_masked") or "")
    if not target_hash and raw_account and _FULL_ACCOUNT.fullmatch(raw_account):
        target_hash = hash_fund_account(raw_account)
    if not target_hash:
        embedded = _FULL_ACCOUNT.findall(text)
        if embedded:
            target_hash = hash_fund_account(embedded[0])
    if target_hash:
        found = [item for item in options if item.fund_account_hash == target_hash]
        if found:
            return _unique_or_error(found)
        if any(item.fund_account_hash for item in options):
            return None, "FUND_ACCOUNT_NOT_FOUND"
    keys = {str(data.get("target_key") or data.get("key") or "")}
    keys.discard("")
    if keys:
        found = [item for item in options if item.key in keys]
        if found:
            return _unique_or_error(found)
    tail = str(data.get("fund_account_tail4") or _tail4(text))
    masked = str(data.get("fund_account_masked") or "")
    text_candidates = []
    for item in options:
        same_text = bool(text) and _norm(text) in {_norm(item._display_text), _norm(item.display_masked)}
        same_masked = bool(masked) and _norm(masked) == _norm(item.fund_account_masked)
        if same_text or same_masked:
            text_candidates.append(item)
    if tail:
        tail_candidates = [item for item in options if item.fund_account_tail4 == tail]
        found = [item for item in text_candidates if item.fund_account_tail4 == tail] if text_candidates else tail_candidates
    else:
        found = text_candidates
    unique = []
    for item in found:
        if item not in unique:
            unique.append(item)
    if unique:
        return _unique_or_error(unique)
    identity_key = _display_identity_key(text)
    if identity_key:
        identity_matches = [
            item for item in options
            if identity_key in {
                _display_identity_key(item._display_text),
                _display_identity_key(item.display_masked),
            }
        ]
        if identity_matches:
            return _unique_or_error(identity_matches)
    if not allow_fuzzy:
        return None, "FUND_ACCOUNT_NOT_FOUND"
    fuzzy_target = _masked_from_label(text) or masked
    return _masked_fuzzy_match(options, fuzzy_target)

def _unique_or_error(found: Sequence[FundAccountRef]) -> tuple[FundAccountRef | None, str]:
    if len(found) == 1:
        return found[0], ""
    return None, "FUND_ACCOUNT_AMBIGUOUS" if found else "FUND_ACCOUNT_NOT_FOUND"

@dataclass(frozen=True)
class FundAccountRef:
    """资金账户安全标识；原始行文本和完整资金账号只留内存，不出返回值。"""

    index: int
    key: str
    display_masked: str
    fund_account_hash: str = ""
    fund_account_masked: str = ""
    fund_account_tail4: str = ""
    row_kind: str = "unknown"
    login_required: bool = False
    _display_text: str = field(default="", repr=False, compare=False)
    _fund_account: str = field(default="", repr=False, compare=False)

    @classmethod
    def from_label(cls, index: int, label: str) -> "FundAccountRef":
        text = _clean_account_label(label)
        if not text:
            raise AutoIpoError(
                "FUND_ACCOUNT_ROW_EMPTY",
                "同花顺主界面账户下拉存在空行",
                "清理客户端账户下拉后重试",
                {"index": index},
            )
        found = _FULL_ACCOUNT.findall(text)
        raw = found[0] if found else ""
        digest = hash_fund_account(raw) if raw else ""
        key = digest or hash_fund_account(_norm(text))[:20]
        row_kind = _menu_row_kind(text)
        return cls(
            index=int(index),
            key=key,
            display_masked=_masked_from_label(text),
            fund_account_hash=digest,
            fund_account_masked=mask_fund_account(raw) if raw else _masked_from_label(text),
            fund_account_tail4=(raw[-4:] if raw else _tail4(text)),
            row_kind=row_kind,
            login_required=row_kind == "login_required",
            _display_text=text,
            _fund_account=raw,
        )

    def safe_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "target_key": self.key,
            "display_text": self.display_masked,
            "fund_account_hash": self.fund_account_hash,
            "fund_account_masked": self.fund_account_masked,
            "fund_account_tail4": self.fund_account_tail4,
            "row_kind": self.row_kind,
            "login_required": self.login_required,
        }

@dataclass
class FundAccountLoginResult:
    target_key: str
    display_text: str
    fund_account_hash: str
    fund_account_masked: str
    fund_account_tail4: str
    row_kind: str
    login_required: bool
    status: str
    dialog_required: bool = False
    manual_required: bool = False
    xiadan_present: bool = False
    identity_verified_by: str = ""
    failure_stage: str = ""
    clicked_row_masked: str = ""
    menu_row_index: int = -1
    clicked_x: int = -1
    clicked_y: int = -1
    menu_row_rect: tuple[int, int, int, int] = ()
    menu_source: str = ""
    xiadan_labels_masked: list[str] = field(default_factory=list)
    observed_current_masked: str = ""
    observed_display_masked: str = ""
    error_code: str = ""
    error: str = ""
    auto_fill: str = ""  # 登录弹窗自动填充结果：captcha/password/失败原因串

    @property
    def login_status(self) -> str:
        return self.status

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_key": self.target_key,
            "display_text": self.display_text,
            "fund_account_hash": self.fund_account_hash,
            "fund_account_masked": self.fund_account_masked,
            "fund_account_tail4": self.fund_account_tail4,
            "row_kind": self.row_kind,
            "login_required": self.login_required,
            "status": self.status,
            "dialog_required": self.dialog_required,
            "manual_required": self.manual_required,
            "xiadan_present": self.xiadan_present,
            "identity_verified_by": self.identity_verified_by,
            "failure_stage": self.failure_stage,
            "clicked_row_masked": self.clicked_row_masked,
            "menu_row_index": self.menu_row_index,
            "clicked_x": self.clicked_x,
            "clicked_y": self.clicked_y,
            "menu_row_rect": list(self.menu_row_rect),
            "menu_source": self.menu_source,
            "xiadan_labels_masked": list(self.xiadan_labels_masked),
            "observed_current_masked": self.observed_current_masked,
            "observed_display_masked": self.observed_display_masked,
            "error_code": self.error_code,
            "error": _safe(self.error),
            "auto_fill": self.auto_fill,
        }

