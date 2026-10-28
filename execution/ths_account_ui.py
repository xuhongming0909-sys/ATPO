# AI-SUMMARY: 同花顺主界面资金账户发现与委托弹窗处置——统一编排动态登录和身份复核
from __future__ import annotations

import re
import time
import math
from collections.abc import Callable, Mapping, Sequence
from difflib import SequenceMatcher
from typing import Any

from execution.account_session import hash_fund_account
from execution.client_registry import ClientSpec
from execution.ths_account_model import (
    FundAccountLoginResult,
    FundAccountRef,
    _FULL_ACCOUNT,
    _clean_account_label,
    _masked_account_parts,
    _masked_from_label,
    _display_identity_key,
    _masked_match_text,
    _norm,
    _observed_masked,
    _safe,
    _USERNAME_TOKEN,
    match_fund_account,
)
from execution.ths_account_switch import SWITCH_ACCOUNT_ACTION, ThsUI
from execution.ths_account_windows import HexinSwitchUI, _command_lines_for_pids
from shared.errors import AutoIpoError

class ThsAccountUI:
    """ThsUI 真实适配器 + 同花顺主界面资金账户发现/点击/登录复核。"""

    def __init__(
        self,
        client: ClientSpec,
        cfg: Mapping[str, Any],
        *,
        known_ths_accounts: Sequence[str] = (),
        switch_ui: ThsUI | None = None,
        current_account_name_fn: Callable[[], str] | None = None,
        open_menu_fn: Callable[[], object] | None = None,
        read_rows_fn: Callable[[object], Sequence[Mapping[str, Any]]] | None = None,
        click_row_fn: Callable[[object, Mapping[str, Any], int], None] | None = None,
        close_menu_fn: Callable[[], None] | None = None,
        dialog_records_fn: Callable[[ClientSpec, dict], Sequence[Mapping[str, Any]]] | None = None,
        close_login_dialog_fn: Callable[[Sequence[Mapping[str, Any]], dict, ClientSpec], bool] | None = None,
        close_dialog_fn: Callable[[Sequence[Mapping[str, Any]], dict, ClientSpec], bool] | None = None,
        close_modal_fn: Callable[[ClientSpec], int] | None = None,
        ensure_xiadan_fn: Callable[..., None] | None = None,
        current_value_fn: Callable[[ClientSpec], str] | None = None,
        main_window_fn: Callable[[ClientSpec], Any] | None = None,
        account_combo_fn: Callable[[ClientSpec], Any] | None = None,
        switch_account_fn: Callable[[str, float, ClientSpec], None] | None = None,
        open_row_fn: Callable[[Any, int, int, ClientSpec], None] | None = None,
        command_line_fn: Callable[[set[int]], Sequence[str]] | None = None,
        screenshot_fn: Callable[[str], object] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        from execution import hexin_login, login

        self.client = client
        self.cfg = dict(cfg or {})
        self.known_ths_accounts = tuple(str(v).strip() for v in known_ths_accounts if str(v).strip())
        self._switch_ui = switch_ui
        self._current_account_name_fn = current_account_name_fn
        self._open_menu_fn = open_menu_fn or (lambda: hexin_login._default_open_menu(self._hexin_settings(), client))
        self._read_rows_fn = read_rows_fn or (
            lambda menu: hexin_login.read_menu_rows(menu, self._hexin_settings())
        )
        self._click_row_fn = click_row_fn or (
            lambda menu, row, total: hexin_login._default_click_row(menu, row, total, self._hexin_settings())
        )
        self._close_menu_fn = close_menu_fn or hexin_login._default_close_menu
        self._dialog_records_fn = dialog_records_fn or (
            lambda spec, settings: hexin_login._default_dialog_records(spec, settings)
        )
        self._close_login_dialog_fn = (
            close_dialog_fn or close_login_dialog_fn or hexin_login._default_close_login_dialog
        )
        self._close_modal_fn = close_modal_fn or login.close_modal_dialogs
        self._ensure_xiadan_fn = ensure_xiadan_fn or login.ensure_xiadan_ready
        self._current_value_fn = current_value_fn or login._current_fund_account
        self._main_window_fn = main_window_fn or login._main_window
        self._account_combo_fn = account_combo_fn or login._account_combo
        self._switch_account_fn = switch_account_fn or login._switch_to_account
        self._open_row_fn = open_row_fn or login._open_dropdown_and_click_row
        self._command_line_fn = command_line_fn or _command_lines_for_pids
        self._screenshot_fn = screenshot_fn or self._default_screenshot
        raw_sleep = sleep_fn or time.sleep
        self._deadline: float | None = None

        def _bounded_sleep(seconds: float) -> None:
            if self._deadline is not None:
                remaining = self._deadline - time.monotonic()
                if remaining <= 0:
                    raise AutoIpoError(
                        "FUND_ACCOUNT_TIMEOUT",
                        "资金户处理超过限时，判定失败并跳到下一户",
                        "检查该户登录弹窗/网络；限时在 gui.ths_account_switch.per_fund_timeout_s 调整",
                    )
                seconds = min(float(seconds), remaining)
            raw_sleep(seconds)

        self._sleep = _bounded_sleep
        self._ths_stop_reason = ""
        self._menu_rows: list[dict[str, Any]] = []

    def start_deadline(self, seconds: float) -> None:
        """本户处理硬限时：期间所有 _sleep 到点即抛 FUND_ACCOUNT_TIMEOUT。"""
        self._deadline = time.monotonic() + max(0.0, float(seconds)) if seconds else None

    def clear_deadline(self) -> None:
        self._deadline = None

    @staticmethod
    def _default_screenshot(name: str) -> object:
        from execution.hexin_login import _default_shot

        path = f"ths_accounts/{name}"
        _default_shot(path)
        return path

    def _hexin_settings(self) -> dict:
        return dict((self.cfg.get("gui") or {}).get("hexin_login") or {})

    def _xiadan_settings(self) -> dict:
        return dict((self.cfg.get("gui") or {}).get("xiadan") or {})

    def _switch_settings(self) -> dict:
        return dict((self.cfg.get("gui") or {}).get("ths_account_switch") or {})

    def _control_id(self, key: str) -> int:
        value = self._xiadan_settings().get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise AutoIpoError(
                "THS_CONTROL_ID_MISSING",
                f"缺少 gui.xiadan.{key}",
                "在 config/config.yaml 的 gui.xiadan 配置唯一 ComboBox control_id",
                {"key": key},
            )
        return value

    @staticmethod
    def _edit_handle(edit: Any) -> int:
        value = getattr(edit, "handle", 0) or getattr(getattr(edit, "element_info", None), "handle", 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _control_id_value(control: Any) -> int:
        try:
            return int(control.control_id())
        except Exception:
            value = getattr(getattr(control, "element_info", None), "control_id", -1)
            try:
                return int(value)
            except (TypeError, ValueError):
                return -1

    def _require_unique_combo(self, main: Any, control_id: int, key: str) -> Any:
        if main is None:
            raise AutoIpoError(
                "THS_XIADAN_WINDOW_MISSING",
                "未找到 xiadan 交易主窗",
                "先通过同花顺主界面 F12 启动 xiadan",
                {"key": key},
            )
        candidates = [
            item
            for item in main.descendants(class_name="ComboBox")
            if self._control_id_value(item) == control_id
        ]
        if len(candidates) != 1:
            raise AutoIpoError(
                "THS_CONTROL_ID_NOT_UNIQUE",
                f"gui.xiadan.{key} 匹配到 {len(candidates)} 个 ComboBox",
                "修正控件 control_id 或关闭重复 xiadan 窗口；禁止按坐标盲选",
                {"key": key, "control_id": control_id, "count": len(candidates)},
            )
        return candidates[0]

    def _combo_texts(self, combo: Any) -> list[str]:
        try:
            return [str(v or "").strip() for v in combo.item_texts() if str(v or "").strip()]
        except Exception as exc:
            raise AutoIpoError(
                "THS_CONTROL_READ_FAILED",
                "读取 xiadan 账户下拉失败",
                "检查 ComboBox 是否仍存在且未被弹窗遮挡",
                {"detail": _safe(exc)},
            ) from None

    def _safe_result(self, ref: FundAccountRef, status: str, **updates: Any) -> FundAccountLoginResult:
        row = FundAccountLoginResult(
            target_key=ref.key,
            display_text=ref.display_masked,
            fund_account_hash=ref.fund_account_hash,
            fund_account_masked=ref.fund_account_masked,
            fund_account_tail4=ref.fund_account_tail4,
            row_kind=ref.row_kind,
            login_required=ref.login_required,
            status=status,
        )
        for key, value in updates.items():
            if hasattr(row, key):
                setattr(row, key, _safe(value) if key == "error" else value)
        return row

    def _dialogs(self) -> list[dict[str, Any]]:
        raw = self._dialog_records_fn(self.client, self._hexin_settings())
        return [dict(item or {}) for item in list(raw or [])]

    def _dialogs_after_click(self, timeout_s: float) -> list[dict[str, Any]]:
        attempts = max(1, int(float(timeout_s) / 0.2) + 1)
        records: list[dict[str, Any]] = []
        for attempt in range(attempts):
            records = self._dialogs()
            if any(self._is_fund_login_row(item) or self._manual_dialog_rows([item]) for item in records):
                return records
            if attempt + 1 < attempts:
                self._sleep(0.2)
        return records

    def _is_fund_login_row(self, row: Mapping[str, Any]) -> bool:
        """资金账户登录窗按窗口结构/特征判定；即使文本含验证码也属登录窗，必须关闭后继续。"""
        if str(row.get("kind") or "") == "login":
            return True
        title = str(row.get("title") or "")
        texts = [str(value or "") for value in (row.get("texts") or [])]
        combined = _norm(" ".join([title, *texts]))
        account_form = any(
            _norm(value) in combined
            for value in ("资金账号", "资金帐号", "证券公司", "帐号", "账号", "信用交易认证")
        )
        password_form = any(
            _norm(value) in combined
            for value in ("交易密码", "认证密码", "密码")
        )
        return account_form and password_form

    def _manual_dialog_rows(self, records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """只有非资金账户登录窗的安全验证/人工弹窗才阻断；不单看“验证码”关键词。"""
        keywords = ("验证码", "动态口令", "短信验证", "身份验证", "人工处理", "安全验证")
        manual = []
        for item in records:
            row = dict(item or {})
            if self._is_fund_login_row(row):
                continue
            text = " ".join(str(row.get(key) or "") for key in ("title", "texts"))
            if str(row.get("kind") or "") == "manual" or any(word in text for word in keywords):
                manual.append(row)
        return manual

    def _close_password_dialogs(self, records: Sequence[Mapping[str, Any]]) -> bool:
        login_rows = [dict(item) for item in records if self._is_fund_login_row(item)]
        if not login_rows:
            return True
        try:
            self._close_login_dialog_fn(login_rows, self._hexin_settings(), self.client)
        except Exception:
            pass
        wait_s = max(0.0, float(self._hexin_settings().get("dialog_close_wait_s", 0.5) or 0))
        for _ in range(3):
            remaining = [
                item for item in self._dialogs()
                if self._is_fund_login_row(item)
            ]
            if not remaining:
                return True
            if wait_s:
                self._sleep(wait_s / 3)
        return False

    @staticmethod
    def _row_text(row: Mapping[str, Any] | str) -> str:
        return str(row.get("text") or "") if isinstance(row, Mapping) else str(row or "")

    def _account_rows(self, raw_rows: Sequence[Mapping[str, Any] | str]) -> list[dict[str, Any]]:
        ignored = {
            _norm(value)
            for value in ((self._hexin_settings().get("ignore_row_texts") or ["编辑账户"]))
        }
        boundaries = {_norm(value) for value in ("添加券商/账户", "添加券商", "免费开户", "自动启动交易")}
        rows: list[dict[str, Any]] = []
        for fallback, raw in enumerate(raw_rows):
            text = _clean_account_label(self._row_text(raw))
            if not text or _norm(text) in ignored:
                continue
            if _norm(text) in boundaries:
                break
            data = dict(raw) if isinstance(raw, Mapping) else {}
            rows.append({
                "index": int(data.get("index", fallback)),
                "text": text,
                "top": data.get("top", fallback),
                "bottom": data.get("bottom"),
                **{
                    key: data[key]
                    for key in ("left", "right", "click_x", "click_y", "source")
                    if key in data
                },
            })
        return rows

    def _max_fund_accounts(self) -> int:
        mode = (self.cfg.get("execution") or {}).get("ths_account_switch") or {}
        value = mode.get("max_fund_accounts_per_ths")
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
            raise AutoIpoError(
                "FUND_ACCOUNT_LIMIT_INVALID",
                "max_fund_accounts_per_ths 必须是 1 到 10 的整数",
                "修改 execution.ths_account_switch.max_fund_accounts_per_ths",
                {"value": value},
            )
        return value

    def discover_fund_accounts(self) -> list[FundAccountRef]:
        """从同花顺主界面右上角账户下拉动态枚举；不读取 config.accounts/menu_row。"""
        menu = None
        try:
            menu = self._open_menu_fn()
            rows = self._account_rows(self._read_rows_fn(menu) or [])
        except Exception as exc:
            raise AutoIpoError(
                "THS_ACCOUNT_MENU_READ_FAILED",
                "读取同花顺主界面账户下拉失败",
                "确认主界面右上角账户下拉可打开且文本可读",
                {"detail": _safe(exc)},
            ) from None
        finally:
            try:
                self._close_menu_fn()
            except Exception:
                pass
        if not rows:
            raise AutoIpoError(
                "THS_ACCOUNT_MENU_EMPTY",
                "同花顺主界面账户下拉未发现资金账户行",
                "确认该 THS 登录账户下存在可操作账户",
            )
        self._menu_rows = rows
        refs = [FundAccountRef.from_label(row["index"], row["text"]) for row in rows]
        priority = {"direct": 0, "unknown": 1, "login_required": 2}
        return sorted(refs, key=lambda ref: (priority.get(ref.row_kind, 1), ref.index))

    def _find_menu_row(
        self,
        ref: FundAccountRef,
        rows: Sequence[Mapping[str, Any]] | None = None,
        total: int | None = None,
    ) -> tuple[dict[str, Any], int]:
        if rows is None:
            menu = self._open_menu_fn()
            try:
                raw_rows = self._read_rows_fn(menu) or []
                rows = self._account_rows(raw_rows)
                total = len(raw_rows)
            finally:
                try:
                    self._close_menu_fn()
                except Exception:
                    pass
        exact = [row for row in rows if _norm(row["text"]) == _norm(ref._display_text)]
        if len(exact) == 1:
            return exact[0], int(total if total is not None else len(rows))
        options = [FundAccountRef.from_label(row["index"], row["text"]) for row in rows]
        matched, code = match_fund_account(options, ref)
        if matched is not None:
            row = next(row for row in rows if int(row["index"]) == int(matched.index))
            return row, int(total if total is not None else len(rows))
        raise AutoIpoError(
            code or "FUND_ACCOUNT_NOT_FOUND",
            "同花顺主界面账户下拉无法唯一定位目标行",
            "按显示文本或脱敏资金账号唯一匹配；禁止按缓存行号盲点",
            {"target_key": ref.key, "count": len(rows)},
        )

    def _click_main_row(self, ref: FundAccountRef) -> dict[str, Any]:
        menu = self._open_menu_fn()
        try:
            cached = list(self._menu_rows or [])
            row = None
            total = 0
            if cached:
                try:
                    row, total = self._find_menu_row(ref, cached, len(cached))
                except Exception:
                    row = None
            if row is None:
                raw_rows = self._read_rows_fn(menu) or []
                rows = self._account_rows(raw_rows)
                row, total = self._find_menu_row(ref, rows, len(raw_rows))
            self._click_row_fn(menu, row, total)
            return dict(row)
        except Exception:
            try:
                self._close_menu_fn()
            except Exception:
                pass
            raise

    def _xiadan_identity(self, max_wait_s: float = 20.0, interval_s: float = 1.0) -> tuple[bool, str, str, list[str]]:
        # xiadan 启动/自动登录期间 combo 暂不可读，界内有界重试而非立即失败
        attempts = max(1, math.ceil(max_wait_s / interval_s))
        for attempt in range(attempts):
            try:
                main = self._main_window_fn(self.client)
                account_combo = self._require_unique_combo(
                    main, self._control_id("account_combo_control_id"), "account_combo_control_id"
                )
                self._require_unique_combo(
                    main, self._control_id("fund_account_control_id"), "fund_account_control_id"
                )
                combo_labels = self._combo_texts(account_combo)
                present = bool(combo_labels)
                current = str(self._current_value_fn(self.client) or "").strip()
                display = str(account_combo.window_text() or "").strip()
                return present, current, display, combo_labels
            except Exception:
                if attempt + 1 >= attempts:
                    raise AutoIpoError(
                        "XIADAN_CONTROL_STALE",
                        "xiadan 控件句柄失效，重新枚举后仍不可用",
                        "等待交易主窗稳定后重试；不得回退到任意 ComboBox",
                    ) from None
                self._sleep(interval_s)

    @staticmethod
    def _masked_account_identity_matches(ref: FundAccountRef, values: Sequence[str]) -> bool:
        wanted_prefix, wanted_tail = _masked_account_parts(
            ref.fund_account_masked or ref.display_masked
        )
        if not wanted_prefix or not wanted_tail:
            return False
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            candidate_prefix, candidate_tail = _masked_account_parts(text)
            prefix_match = (
                candidate_prefix == wanted_prefix
                or (
                    len(candidate_prefix) >= 3
                    and len(wanted_prefix) >= 3
                    and (
                        candidate_prefix.startswith(wanted_prefix)
                        or wanted_prefix.startswith(candidate_prefix)
                    )
                )
            )
            if prefix_match and candidate_tail == wanted_tail:
                return True
            digits = re.sub(r"\D", "", text)
            if _FULL_ACCOUNT.fullmatch(digits):
                if digits.startswith(wanted_prefix) and digits.endswith(wanted_tail):
                    return True
        return False

    @staticmethod
    def _verify_identity_key(value: object) -> str:
        """登录后身份复核专用宽松键：券商名省略"证券"、信用账户"融"后缀视为同一账户。
        注意：菜单点击匹配保持严格（防点错账户），本键只用于复核已登录身份。"""
        import re as _re
        text = _display_identity_key(value)
        text = text.replace("证券", "")
        return _re.sub(r"融$", "", text)

    @staticmethod
    def _display_name_identity_matches(ref: FundAccountRef, values: Sequence[str]) -> bool:
        raw_wanted = ref._display_text or ref.display_masked
        wanted = _masked_match_text(raw_wanted)
        wanted_identity = _display_identity_key(raw_wanted)
        wanted_verify = ThsAccountUI._verify_identity_key(raw_wanted)
        if not wanted and not wanted_identity:
            return False
        for value in values:
            candidate = _masked_match_text(value)
            if candidate and candidate == wanted:
                return True
            if wanted_identity and _display_identity_key(value) == wanted_identity:
                return True
            if wanted_verify and ThsAccountUI._verify_identity_key(value) == wanted_verify:
                return True
            if candidate and SequenceMatcher(None, wanted, candidate).ratio() >= 0.90:
                return True
        return False

    def _identity_source(self, ref: FundAccountRef, current: str, display: str) -> str:
        values = [current, display]
        if ref.fund_account_hash:
            return "fund_account_hash" if current and hash_fund_account(current) == ref.fund_account_hash else ""
        if self._masked_account_identity_matches(ref, values):
            return "masked_account"
        if self._display_name_identity_matches(ref, values):
            return "display_name"
        return ""

    def _identity_matches(self, ref: FundAccountRef, current: str, display: str, labels: Sequence[str]) -> bool:
        return bool(self._identity_source(ref, current, display))

    def _identity_observations(self, current: str, display: str,
                              labels: Sequence[str] = ()) -> dict[str, Any]:
        return {
            "observed_current_masked": _safe(_observed_masked(current)),
            "observed_display_masked": _safe(_observed_masked(display)),
            "xiadan_labels_masked": [
                _safe(_masked_from_label(value)) for value in labels if str(value or "").strip()
            ],
        }

    def _switch_xiadan_target(self, ref: FundAccountRef) -> None:
        """复用 login.py 已验证的真实下拉点行切换能力。"""
        timeout_s = float(self._switch_settings().get("login_wait_s", 0))
        if timeout_s <= 0:
            raise AutoIpoError(
                "THS_GUI_SETTING_INVALID",
                "gui.ths_account_switch.login_wait_s 必须为正数",
                "配置资金账户切换等待上限",
            )
        if ref._fund_account:
            self._switch_account_fn(ref._fund_account, timeout_s, self.client)
            return
        main = self._main_window_fn(self.client)
        combo = self._require_unique_combo(
            main, self._control_id("account_combo_control_id"), "account_combo_control_id"
        )
        all_items = self._combo_texts(combo)
        options = [
            FundAccountRef.from_label(index, text)
            for index, text in enumerate(all_items)
            if "编辑账户" not in text
        ]
        matched, code = match_fund_account(options, ref, allow_fuzzy=False)
        if matched is None:
            raise AutoIpoError(
                code,
                "xiadan 账户下拉无法唯一定位目标资金账户",
                "按脱敏资金账号/显示文本唯一匹配",
                {"target_key": ref.key},
            )
        self._open_row_fn(combo, int(matched.index), len(all_items), self.client)

    def login_fund_account(self, ref: FundAccountRef) -> FundAccountLoginResult:
        """只凭当前资金账号/当前账户显示名复核；下拉列表存在不构成登录成功。"""
        if self._ths_stop_reason:
            return self._safe_result(
                ref,
                self._ths_stop_reason,
                dialog_required=True,
                manual_required=self._ths_stop_reason == "manual_required",
                failure_stage="manual_dialog",
                error_code=self._ths_stop_reason,
                error="当前 THS 已因人工弹窗/弹窗清理失败停止后续资金户",
            )

        try:
            clicked_row = self._click_main_row(ref)
        except Exception as exc:
            code = exc.code if isinstance(exc, AutoIpoError) else "FUND_ACCOUNT_CLICK_FAILED"
            return self._safe_result(
                ref,
                "not_selected",
                failure_stage="menu_click",
                error_code=code,
                error=str(exc),
            )

        clicked_masked = _safe(_masked_from_label(clicked_row.get("text")))
        rect_values = [
            clicked_row.get(key)
            for key in ("left", "top", "right", "bottom")
        ]
        clicked_rect = tuple(int(value) for value in rect_values) if all(
            isinstance(value, (int, float)) for value in rect_values
        ) else ()
        clicked_x = int(clicked_row.get("click_x")) if isinstance(clicked_row.get("click_x"), (int, float)) else -1
        clicked_y = int(clicked_row.get("click_y")) if isinstance(clicked_row.get("click_y"), (int, float)) else -1
        latest_labels: list[str] = []
        initial_identity = False
        try:
            initial_present, initial_current, initial_display, initial_labels = self._xiadan_identity()
            latest_labels[:] = list(initial_labels or [])
            initial_identity = bool(
                initial_present and self._identity_source(ref, initial_current, initial_display)
            )
        except Exception:
            pass

        def finish(
            status: str,
            *,
            failure_stage: str = "",
            current: str = "",
            display: str = "",
            **updates: Any,
        ) -> FundAccountLoginResult:
            values = {
                "failure_stage": failure_stage,
                "clicked_row_masked": clicked_masked,
                "menu_row_index": int(clicked_row.get("index", -1)),
                "clicked_x": clicked_x,
                "clicked_y": clicked_y,
                "menu_row_rect": list(clicked_rect),
                "menu_source": str(clicked_row.get("source") or ""),
                **self._identity_observations(current, display, latest_labels),
                **updates,
            }
            return self._safe_result(ref, status, **values)

        dialog_wait_s = max(0.2, float(self._switch_settings().get("dialog_wait_s", 0.5) or 0.5))

        def handle_dialogs(records: Sequence[Mapping[str, Any]], stage: str) -> FundAccountLoginResult | None:
            copy_rows = [
                item for item in records
                if "拷贝数据" in " ".join(str(item.get(key) or "") for key in ("title", "texts"))
                and "验证码" in " ".join(str(item.get(key) or "") for key in ("title", "texts"))
            ]
            if copy_rows:
                try:
                    from execution.captcha_login import try_captcha_prompt
                    from execution.hexin_login import _hexin_pids
                    from execution.login import _xiadan_pids

                    pids = _hexin_pids(self.client) | _xiadan_pids(self.client)
                    if try_captcha_prompt(pids):
                        return None
                except Exception:
                    pass
            login_rows = [item for item in records if self._is_fund_login_row(item)]
            if login_rows:
                self._screenshot_fn(f"fund_login/{ref.key}_dialog.png")
                combined = " ".join(
                    str(r.get(k) or "") for r in login_rows for k in ("title", "texts")
                )
                from execution.hexin_login import _hexin_pids
                from execution.login import _xiadan_pids

                try:
                    pids = _hexin_pids(self.client) | _xiadan_pids(self.client)
                except Exception:
                    pids = set()
                fill_notes: list[str] = []
                # ① OCR 验证码直填：不再要求弹窗记录文本含"验证码"（记录常不含，2026-10-26 用户拍板：能登就登）
                try:
                    from execution.captcha_login import try_captcha_login

                    if try_captcha_login(pids, notes=fill_notes, attempts=1):
                        self._sleep(2.0)
                        try:
                            present, current, display, labels = self._xiadan_identity()
                            latest_labels[:] = list(labels or [])
                            source = self._identity_source(ref, current, display)
                            if present and source:
                                return finish(
                                    "ready",
                                    failure_stage=stage,
                                    current=current,
                                    display=display,
                                    xiadan_present=True,
                                    identity_verified_by=source,
                                    auto_fill="captcha",
                                )
                        except Exception:
                            pass
                    fill_notes.append("captcha_fill_failed")
                except Exception:
                    fill_notes.append("captcha_fill_error")
                # ② DPAPI 密码填充：客户端已存密码的户（如华宝），补验证码+点登录
                try:
                    import re as _re

                    from execution.captcha_login import password_for_fund_account, try_password_login

                    match = _re.search(r"\d{6,}", combined)
                    password = password_for_fund_account(match.group(0) if match else "")
                    if not password:
                        fill_notes.append("no_dpapi_password")
                    elif try_password_login(pids, password):
                        self._sleep(2.0)
                        try:
                            present, current, display, labels = self._xiadan_identity()
                            latest_labels[:] = list(labels or [])
                            source = self._identity_source(ref, current, display)
                            if present and source:
                                return finish(
                                    "ready",
                                    failure_stage=stage,
                                    current=current,
                                    display=display,
                                    xiadan_present=True,
                                    identity_verified_by=source,
                                    auto_fill="password",
                                )
                        except Exception:
                            pass
                    else:
                        fill_notes.append("password_fill_failed")
                except Exception:
                    fill_notes.append("password_fill_error")
                # 自动填充均失败：留证（截图+原因）后关框跳过——真正无法登录才跳过
                self._screenshot_fn(f"fund_login/{ref.key}_after_fill.png")
                closed = self._close_password_dialogs(login_rows)
                if not closed:
                    self._ths_stop_reason = "dialog_cleanup_failed"
                    return finish(
                        "dialog_cleanup_failed",
                        failure_stage=stage,
                        login_required=True,
                        dialog_required=True,
                        manual_required=True,
                        error_code="dialog_cleanup_failed",
                        error="登录弹窗未能确认完全消失，当前 THS 后续资金户停止",
                    )
                if self._manual_dialog_rows(self._dialogs()):
                    self._ths_stop_reason = "manual_required"
                    self._screenshot_fn(f"fund_login/{ref.key}_manual_dialog.png")
                    return finish(
                        "manual_required",
                        failure_stage="manual_dialog",
                        login_required=True,
                        dialog_required=True,
                        manual_required=True,
                        error_code="FUND_MANUAL_DIALOG",
                        error="出现人工/安全验证弹窗，未自动关闭，当前 THS 后续资金户停止",
                    )
                post_wait_s = max(
                    0.0,
                    float(self._switch_settings().get("post_dialog_result_wait_s", 5) or 0),
                )
                poll_interval_s = max(
                    0.1,
                    float(self._switch_settings().get("post_dialog_poll_interval_s", 0.5) or 0.5),
                )
                last_current = ""
                last_display = ""
                last_present = False
                for _attempt in range(max(1, math.ceil(post_wait_s / poll_interval_s)) if post_wait_s else 1):
                    try:
                        last_present, last_current, last_display, labels = self._xiadan_identity()
                        latest_labels[:] = list(labels or [])
                        identity_source = self._identity_source(ref, last_current, last_display)
                        if not initial_identity and last_present and identity_source:
                            return finish(
                                "ready",
                                failure_stage=stage,
                                current=last_current,
                                display=last_display,
                                xiadan_present=True,
                                identity_verified_by=identity_source,
                            )
                    except Exception:
                        pass
                    if self._manual_dialog_rows(self._dialogs()):
                        break
                    if post_wait_s:
                        self._sleep(poll_interval_s)
                return finish(
                    "dialog_closed",
                    failure_stage=stage,
                    current=last_current,
                    display=last_display,
                    xiadan_present=last_present,
                    login_required=True,
                    dialog_required=True,
                    manual_required=False,
                    error_code="FUND_LOGIN_DIALOG_CLOSED",
                    error="资金账户登录弹窗已确认关闭，继续下一个可直登账户",
                    auto_fill=";".join(fill_notes) if fill_notes else "not_attempted",
                )
            if self._manual_dialog_rows(records):
                self._ths_stop_reason = "manual_required"
                self._screenshot_fn(f"fund_login/{ref.key}_manual_dialog.png")
                return finish(
                    "manual_required",
                    failure_stage="manual_dialog",
                    login_required=True,
                    dialog_required=True,
                    manual_required=True,
                    error_code="FUND_MANUAL_DIALOG",
                    error="出现人工/安全验证弹窗，未自动关闭，当前 THS 后续资金户停止",
                )
            return None

        records = self._dialogs_after_click(dialog_wait_s)
        dialog_result = handle_dialogs(records, "fund_login_dialog")
        if dialog_result is not None:
            return dialog_result

        try:
            self._ensure_xiadan_fn(client=self.client)
            present, current, display, labels = self._xiadan_identity()
            latest_labels[:] = list(labels or [])
        except Exception as exc:
            code = exc.code if isinstance(exc, AutoIpoError) else "XIADAN_MISSING"
            self._screenshot_fn(f"fund_login/{ref.key}_xiadan_failed.png")
            return finish(
                "xiadan_failed",
                failure_stage="xiadan_prepare",
                error_code=code,
                error=str(exc),
            )

        if not present:
            return finish(
                "xiadan_failed",
                failure_stage="xiadan_identity",
                current=current,
                display=display,
                error_code="XIADAN_ACCOUNT_LIST_MISSING",
                error="xiadan 账户列表不可见",
            )

        identity_source = self._identity_source(ref, current, display)
        if identity_source:
            return finish(
                "ready",
                current=current,
                display=display,
                xiadan_present=True,
                identity_verified_by=identity_source,
            )

        result_wait_s = float(self._switch_settings().get("fund_login_result_wait_s", 0) or 0)
        poll_interval_s = float(self._switch_settings().get("fund_login_poll_interval_s", 0) or 0)
        if result_wait_s <= 0 or poll_interval_s <= 0:
            raise AutoIpoError(
                "THS_GUI_SETTING_INVALID",
                "资金账户登录结果等待参数必须为正数",
                "配置 fund_login_result_wait_s 和 fund_login_poll_interval_s",
            )
        attempts = max(1, math.ceil(result_wait_s / poll_interval_s))
        switch_error: Exception | None = None
        switch_code = ""
        switched = False
        for round_no in range(2):
            for attempt in range(attempts):
                records = self._dialogs_after_click(min(0.2, dialog_wait_s))
                dialog_result = handle_dialogs(records, "fund_login_result_dialog")
                if dialog_result is not None:
                    return dialog_result
                try:
                    self._switch_xiadan_target(ref)
                    switched = True
                    break
                except Exception as exc:
                    switch_error = exc
                    switch_code = exc.code if isinstance(exc, AutoIpoError) else "FUND_ACCOUNT_SWITCH_FAILED"
                    if switch_code not in {
                        "FUND_ACCOUNT_NOT_FOUND",
                        "FUND_ACCOUNT_AMBIGUOUS",
                        "XIADAN_ACCOUNT_NOT_FOUND",
                        "XIADAN_ACCOUNT_AMBIGUOUS",
                    }:
                        break
                    if attempt + 1 < attempts:
                        self._sleep(poll_interval_s)
            if switched or switch_code not in {"FUND_ACCOUNT_NOT_FOUND", "XIADAN_ACCOUNT_NOT_FOUND"}:
                break
            if round_no == 0:
                # 首轮点击可能未生效，补点一次主界面菜单行再查一轮
                try:
                    self._click_main_row(ref)
                except Exception:
                    break
        if not switched:
            self._screenshot_fn(f"fund_login/{ref.key}_switch_failed.png")
            if switch_code in {"FUND_ACCOUNT_NOT_FOUND", "XIADAN_ACCOUNT_NOT_FOUND"}:
                return finish(
                    "not_logged_in",
                    failure_stage="fund_login_result",
                    current=current,
                    display=display,
                    xiadan_present=True,
                    error_code="FUND_ACCOUNT_NOT_FOUND",
                    error="主界面点击后目标账户未进入 xiadan 已登录列表",
                )
            return finish(
                "switch_failed",
                failure_stage="xiadan_switch",
                current=current,
                display=display,
                xiadan_present=True,
                error_code=switch_code or "FUND_ACCOUNT_SWITCH_FAILED",
                error=str(switch_error or ""),
            )

        records = self._dialogs_after_click(dialog_wait_s)
        dialog_result = handle_dialogs(records, "xiadan_switch_dialog")
        if dialog_result is not None:
            return dialog_result

        try:
            present, current, display, labels = self._xiadan_identity()
            latest_labels[:] = list(labels or [])
        except Exception as exc:
            code = exc.code if isinstance(exc, AutoIpoError) else "XIADAN_CONTROL_STALE"
            return finish(
                "xiadan_failed",
                failure_stage="xiadan_identity",
                current=current,
                display=display,
                error_code=code,
                error=str(exc),
            )

        identity_source = self._identity_source(ref, current, display)
        if present and identity_source:
            return finish(
                "ready",
                current=current,
                display=display,
                xiadan_present=True,
                identity_verified_by=identity_source,
            )

        late_records = self._dialogs_after_click(min(1.0, dialog_wait_s))
        dialog_result = handle_dialogs(late_records, "late_login_dialog")
        if dialog_result is not None:
            return dialog_result

        self._screenshot_fn(f"fund_login/{ref.key}_wrong_account.png")
        return finish(
            "wrong_account",
            failure_stage="identity_verify",
            current=current,
            display=display,
            xiadan_present=True,
            error_code="FUND_ACCOUNT_VERIFY_FAILED",
            error="主界面点击或 xiadan 切户后当前资金账号/账户显示名与目标不一致；未凭下拉列表判成功",
        )
    def ensure_xiadan_ready(self) -> None:
        self._ensure_xiadan_fn(client=self.client)

    def save_screenshot(self, name: str) -> object:
        return self._screenshot_fn(name)

    def _delegate_ui(self) -> ThsUI:
        if self._switch_ui is None:
            self._switch_ui = HexinSwitchUI(
                self.client,
                self.cfg,
                known_ths_accounts=self.known_ths_accounts,
                command_line_fn=self._command_line_fn,
                screenshot_fn=self._screenshot_fn,
                sleep_fn=self._sleep,
            )
        return self._switch_ui

    def current_account_name(self) -> str:
        if self._current_account_name_fn is not None:
            return self._current_account_name_fn()
        return self._delegate_ui().current_account_name()

    def current_main_account_name(self) -> str:
        if self._current_account_name_fn is not None:
            return self._current_account_name_fn()
        return self._delegate_ui().current_main_account_name()

    def close_main_window(self) -> None:
        self._delegate_ui().close_main_window()

    def wait_for_popup(self, timeout_s: float, action: str = SWITCH_ACCOUNT_ACTION) -> bool:
        return self._delegate_ui().wait_for_popup(timeout_s, action)

    def click_popup(self, action: str) -> bool:
        return self._delegate_ui().click_popup(action)

    def wait_for_client_exit(self, timeout_s: float) -> bool:
        return self._delegate_ui().wait_for_client_exit(timeout_s)

    def wait_for_login_window(self, timeout_s: float) -> bool:
        return self._delegate_ui().wait_for_login_window(timeout_s)

    def open_account_dropdown(self) -> None:
        self._delegate_ui().open_account_dropdown()

    def account_display_names(self) -> Sequence[str]:
        return self._delegate_ui().account_display_names()

    def select_account(self, username: str) -> None:
        self._delegate_ui().select_account(username)

    def password_has_text(self) -> bool:
        return self._delegate_ui().password_has_text()

    def set_password(self, password: str) -> None:
        self._delegate_ui().set_password(password)

    def click_login(self) -> bool:
        return self._delegate_ui().click_login()

    def wait_for_main_window(self, timeout_s: float) -> bool:
        return self._delegate_ui().wait_for_main_window(timeout_s)

