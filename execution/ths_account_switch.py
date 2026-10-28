# AI-SUMMARY: 同花顺登录账户切换核心状态机——按显示名唯一选户、密码单次补填、结构化失败与截图留痕
from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from shared.errors import AutoIpoError

MAX_THS_LOGIN_ACCOUNTS = 10
SWITCH_ACCOUNT_ACTION = "切换账号"
EXIT_ACTION = "退出"
ES_PASSWORD = 0x0020
_PASSWORD_FORBIDDEN_METADATA = frozenset({
    "text", "value", "window_text", "texts", "content", "password", "password_text",
})


@dataclass(frozen=True)
class ThsLoginAccount:
    """同花顺登录账户；唯一身份就是客户端显示名。"""

    username: str

    def __post_init__(self) -> None:
        username = str(self.username or "").strip()
        if not username:
            raise AutoIpoError(
                "THS_ACCOUNT_CONFIG_INVALID",
                "同花顺账户 username 不能为空",
                "配置客户端显示名 username，不配置自定义 ID 或别名",
            )
        object.__setattr__(self, "username", username)


@dataclass(frozen=True)
class ThsAccountSwitchResult:
    username: str
    status: str


@dataclass(frozen=True)
class PasswordEditControl:
    """脱敏密码控件指纹；只保存稳定控件元数据，不保存 Edit 文本或值。"""

    control_id: int
    style: int
    rectangle: tuple[int, int, int, int]
    visible: bool = True
    password_hint: bool = False

    def safe_metadata(self) -> dict[str, Any]:
        return {
            "control_id": self.control_id,
            "style": self.style,
            "rectangle": list(self.rectangle),
            "visible": self.visible,
            "password_hint": self.password_hint,
        }


@runtime_checkable
class ThsUI(Protocol):
    """状态机所需 UI 能力；真实控件、截图和等待由实现方注入。"""

    def current_account_name(self) -> str: ...
    def close_main_window(self) -> None: ...
    def wait_for_popup(self, timeout_s: float, action: str = "") -> bool: ...
    def click_popup(self, action: str) -> bool: ...
    def wait_for_client_exit(self, timeout_s: float) -> bool: ...
    def wait_for_login_window(self, timeout_s: float) -> bool: ...
    def open_account_dropdown(self) -> None: ...
    def account_display_names(self) -> Iterable[str]: ...
    def select_account(self, username: str) -> None: ...
    def password_has_text(self) -> bool: ...
    def set_password(self, password: str) -> None: ...
    def click_login(self) -> None: ...
    def wait_for_main_window(self, timeout_s: float) -> bool: ...
    def save_screenshot(self, name: str) -> object: ...


class PasswordControlUI(Protocol):
    """密码控件最小接口；只返回控件是否已填，不读取或返回实际内容。"""

    def password_edit_controls(self) -> Iterable[Mapping[str, Any]]: ...
    def password_control_filled(self, control: PasswordEditControl) -> bool: ...
    def set_password_control(self, control: PasswordEditControl, password: str) -> None: ...


ThsAccountSwitchUI = ThsUI


def _password_metadata_error(
    code: str,
    message: str,
    hint: str,
    **context: Any,
) -> AutoIpoError:
    return AutoIpoError(code, message, hint, dict(context))


def _is_stale_handle_error(exc: Exception) -> bool:
    if isinstance(exc, AutoIpoError):
        return exc.code.endswith("_HANDLE_STALE")
    name = type(exc).__name__.lower()
    detail = str(exc).lower()
    markers = (
        "invalidwindowhandle",
        "invalid window handle",
        "not a valid window handle",
        "not a vaild window handle",
        "stale handle",
    )
    return any(marker in name or marker in detail for marker in markers)


def _stale_password_control_error(index: int) -> AutoIpoError:
    return _password_metadata_error(
        "THS_PASSWORD_CONTROL_HANDLE_STALE",
        "登录窗口控件句柄已失效",
        "重新识别同花顺登录窗口后重试；不读取或输出 Edit 文本",
        candidate_index=index,
    )


def _metadata_roots(item: Any) -> list[Any]:
    if not isinstance(item, Mapping):
        roots = [item]
    else:
        roots = [item]
        for key in ("control", "edit", "element_info"):
            value = item.get(key)
            if value is not None:
                roots.append(value)
    for root in list(roots):
        element_info = getattr(root, "element_info", None)
        if element_info is not None:
            roots.append(element_info)
    return roots


def _metadata_value(item: Any, names: tuple[str, ...]) -> tuple[Any, bool]:
    stale = False
    for root in _metadata_roots(item):
        for name in names:
            try:
                if isinstance(root, Mapping):
                    value = root.get(name)
                else:
                    value = getattr(root, name, None)
                    if callable(value):
                        value = value()
            except Exception as exc:
                stale = stale or _is_stale_handle_error(exc)
                continue
            if value is not None:
                return value, stale
    return None, stale


def _win32_value(name: str, *args: int) -> tuple[Any, bool]:
    try:
        import win32gui

        function = getattr(win32gui, name)
        return function(*args), False
    except Exception as exc:
        return None, _is_stale_handle_error(exc)


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _rectangle_value(value: Any) -> tuple[int, int, int, int] | None:
    if isinstance(value, Mapping):
        values = tuple(value.get(key) for key in ("left", "top", "right", "bottom"))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = tuple(value)
    else:
        values = tuple(getattr(value, key, None) for key in ("left", "top", "right", "bottom"))
    if len(values) != 4:
        return None
    parsed = tuple(_int_value(item) for item in values)
    if any(item is None for item in parsed):
        return None
    left, top, right, bottom = parsed
    if left >= right or top >= bottom:
        return None
    return left, top, right, bottom


def _visible_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


def _password_hint_value(item: Any) -> bool:
    value, _stale = _metadata_value(item, ("password_hint", "is_password"))
    if callable(value):
        try:
            value = value()
        except Exception:
            return False
    return _visible_value(value) is True


def _parse_password_control(item: Any, index: int) -> PasswordEditControl:
    if isinstance(item, Mapping):
        forbidden = sorted(
            _PASSWORD_FORBIDDEN_METADATA.intersection(str(key).lower() for key in item)
        )
        if forbidden:
            raise _password_metadata_error(
                "THS_PASSWORD_CONTROL_METADATA_INVALID",
                "Edit 元数据禁止包含文本或值字段",
                "只传稳定控件元数据；禁止读取或传递 Edit 内容",
                candidate_index=index,
                forbidden_fields=forbidden,
            )

    stale = False
    handle_raw, value_stale = _metadata_value(item, ("handle",))
    stale = stale or value_stale
    handle = _int_value(handle_raw)
    if handle_raw is not None and handle is None:
        raise _password_metadata_error(
            "THS_PASSWORD_CONTROL_METADATA_INVALID",
            "Edit handle 格式无效",
            "handle 必须是整数；缺失时可由 control_id/style/rectangle 识别",
            candidate_index=index,
        )
    if handle is not None and handle < 0:
        raise _password_metadata_error(
            "THS_PASSWORD_CONTROL_METADATA_INVALID",
            "Edit handle 不能为负数",
            "重新识别登录窗口控件后重试",
            candidate_index=index,
        )

    control_id_raw, value_stale = _metadata_value(item, ("control_id",))
    stale = stale or value_stale
    control_id = _int_value(control_id_raw)
    if control_id_raw is not None and (control_id is None or control_id < 0):
        control_id = None
    if control_id is None and handle is not None:
        control_id_raw, value_stale = _win32_value("GetDlgCtrlID", handle)
        stale = stale or value_stale
        control_id = _int_value(control_id_raw)
        if control_id is not None and control_id < 0:
            control_id = None
    if control_id is None:
        control_id = 0

    style_raw, value_stale = _metadata_value(item, ("style",))
    stale = stale or value_stale
    style = _int_value(style_raw)
    if style_raw is not None and style is None:
        raise _password_metadata_error(
            "THS_PASSWORD_CONTROL_METADATA_INVALID",
            "Edit style 格式无效",
            "style 必须是整数；缺失时可由有效 handle 读取",
            candidate_index=index,
        )
    if style is None and handle is not None:
        style_raw, value_stale = _win32_value("GetWindowLongW", handle, -16)
        stale = stale or value_stale
        style = _int_value(style_raw)
    password_hint = _password_hint_value(item)
    if style is None:
        style = ES_PASSWORD if password_hint else 0

    rectangle_raw, value_stale = _metadata_value(item, ("rectangle",))
    stale = stale or value_stale
    rectangle = _rectangle_value(rectangle_raw)
    if rectangle_raw is not None and rectangle is None:
        raise _password_metadata_error(
            "THS_PASSWORD_CONTROL_METADATA_INVALID",
            "Edit rectangle 格式无效",
            "rectangle 提供 left/top/right/bottom，且 right/bottom 必须大于 left/top",
            candidate_index=index,
        )
    if rectangle is None:
        if stale:
            raise _stale_password_control_error(index)
        raise _password_metadata_error(
            "THS_PASSWORD_CONTROL_METADATA_INVALID",
            "无法解析 Edit rectangle",
            "提供稳定 rectangle 后再选择密码框",
            candidate_index=index,
        )

    visible_raw, value_stale = _metadata_value(item, ("visible", "is_visible"))
    stale = stale or value_stale
    visible = _visible_value(visible_raw)
    if visible_raw is not None and visible is None:
        raise _password_metadata_error(
            "THS_PASSWORD_CONTROL_METADATA_INVALID",
            "Edit visible 格式无效",
            "visible 使用布尔值或 0/1",
            candidate_index=index,
        )
    if visible is None:
        if stale:
            raise _stale_password_control_error(index)
        visible = True

    return PasswordEditControl(
        control_id=control_id,
        style=style,
        rectangle=rectangle,
        visible=visible,
        password_hint=password_hint,
    )


def select_password_edit(controls: Iterable[Any]) -> PasswordEditControl:
    """按脱敏稳定元数据唯一选择密码框；兼容多种控件元数据来源。

    优先读取显式 control_id，其次 control.control_id() / element_info.control_id，
    最后使用有效 handle 调 GetDlgCtrlID。只读取控件定位元数据，绝不读取或返回
    Edit 文本、value、password。
    """
    rows = list(controls or [])
    visible_controls: dict[tuple[int, tuple[int, int, int, int]], PasswordEditControl] = {}
    password_controls: list[PasswordEditControl] = []
    for index, item in enumerate(rows):
        control = _parse_password_control(item, index)
        if not control.visible:
            continue
        fingerprint = (control.control_id, control.style, control.rectangle, control.password_hint)
        if fingerprint in visible_controls:
            raise _password_metadata_error(
                "THS_PASSWORD_CONTROL_METADATA_INVALID",
                "可见 Edit 的稳定元数据不唯一",
                "确认登录窗口 control_id/rectangle 唯一；禁止按坐标盲选",
                control_id=control.control_id,
                rectangle=list(control.rectangle),
            )
        visible_controls[fingerprint] = control
        if control.style & ES_PASSWORD or control.password_hint:
            password_controls.append(control)

    if not password_controls:
        raise _password_metadata_error(
            "THS_PASSWORD_CONTROL_NOT_FOUND",
            "未找到带 ES_PASSWORD style 的可见密码框",
            "检查登录窗口 Edit 的 style/rectangle/control_id；不要用其他 Edit 代替",
            candidate_count=len(rows),
            visible_edit_count=len(visible_controls),
        )
    if len(password_controls) > 1:
        raise _password_metadata_error(
            "THS_PASSWORD_CONTROL_AMBIGUOUS",
            f"密码框选择存在 {len(password_controls)} 个候选",
            "补充稳定的 control_id/位置特征后唯一识别；禁止按坐标盲选",
            candidate_count=len(password_controls),
            candidates=[control.safe_metadata() for control in password_controls],
        )
    return password_controls[0]


def _username(value: ThsLoginAccount | str | None) -> str:
    if value is None:
        return ""
    raw = value.username if isinstance(value, ThsLoginAccount) else str(value)
    return raw.strip()


def _enabled_accounts(configured: Sequence[ThsLoginAccount | str | Mapping[str, Any]]) -> list[ThsLoginAccount]:
    accounts: list[ThsLoginAccount] = []
    seen: set[str] = set()
    for item in configured:
        if isinstance(item, Mapping):
            if item.get("enabled", True) is False:
                continue
            username = item.get("username")
        else:
            username = item
        account = ThsLoginAccount(username=_username(username))
        if account.username in seen:
            raise AutoIpoError(
                "THS_ACCOUNT_CONFIG_INVALID",
                f"同花顺账户显示名重复：{account.username}",
                "客户端显示名必须唯一；不要配置 ID 或别名绕过重复",
                {"username": account.username},
            )
        seen.add(account.username)
        accounts.append(account)
    return accounts


def select_next_account(
    current: ThsLoginAccount | str | None,
    configured: Sequence[ThsLoginAccount | str | Mapping[str, Any]],
    enabled_limit: int = 10,
) -> ThsLoginAccount | None:
    """按配置顺序返回当前账户的下一项；当前不在配置中则从首项开始。"""
    if isinstance(enabled_limit, bool) or not isinstance(enabled_limit, int) or not 1 <= enabled_limit <= MAX_THS_LOGIN_ACCOUNTS:
        raise AutoIpoError(
            "THS_ACCOUNT_LIMIT_EXCEEDED",
            "enabled_limit 必须是 1 到 10 的整数",
            "将 max_ths_accounts / enabled_limit 调整到 10 以内",
            {"enabled_limit": enabled_limit},
        )
    accounts = _enabled_accounts(configured)
    if len(accounts) > MAX_THS_LOGIN_ACCOUNTS:
        raise AutoIpoError(
            "THS_ACCOUNT_LIMIT_EXCEEDED",
            f"配置的同花顺账户数 {len(accounts)} 超过硬上限 10",
            "停用并删除多余账户；单个同花顺客户端最多配置 10 个登录账户",
            {"count": len(accounts), "enabled_limit": MAX_THS_LOGIN_ACCOUNTS},
        )
    accounts = accounts[:enabled_limit]
    current_name = _username(current)
    if not current_name:
        return accounts[0] if accounts else None
    for index, account in enumerate(accounts):
        if account.username == current_name:
            return accounts[index + 1] if index + 1 < len(accounts) else None
    return accounts[0] if accounts else None


def _screenshot(ui: ThsUI, stage: str) -> str:
    try:
        value = ui.save_screenshot(f"ths_account_switch/{stage}.png")
        return str(value) if value else ""
    except Exception:
        return ""


def _fail(
    code: str,
    message: str,
    hint: str,
    *,
    ui: ThsUI | None = None,
    client: object = "",
    target: str = "",
    stage: str = "",
) -> None:
    context: dict[str, Any] = {
        "client": str(client or ""),
        "target": target,
        "stage": stage,
    }
    if ui is not None:
        shot = _screenshot(ui, stage or code.lower())
        if shot:
            context["screenshot"] = shot
    raise AutoIpoError(code, message, hint, context)


def _stage_call(
    stage: str,
    fn: Callable[..., Any],
    *args: Any,
    ui: ThsUI,
    client: object,
    target: str,
    **kwargs: Any,
) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        if _is_stale_handle_error(exc):
            _fail(
                "THS_UI_HANDLE_STALE",
                f"同花顺窗口控件句柄已失效（阶段：{stage}）",
                "重新识别同花顺窗口后重试；不得复用失效控件句柄",
                ui=ui,
                client=client,
                target=target,
                stage=stage,
            )
        raise


def _current_main_account_name(ui: ThsUI) -> str:
    reader = getattr(ui, "current_main_account_name", None)
    return str(reader() if callable(reader) else ui.current_account_name())


_ACCOUNT_READ_RETRY_CODES = {
    "THS_CURRENT_ACCOUNT_OCR_UNMATCHED",
    "THS_CURRENT_ACCOUNT_OCR_FAILED",
    "THS_CURRENT_ACCOUNT_UNREADABLE",
}


def _read_account_until_ready(reader: Callable[[], str], deadline: float) -> str:
    """主窗可能仍在渲染；账户读取类错误在剩余时间内间隔重试，有界不空转。"""
    while True:
        try:
            return str(reader() or "")
        except AutoIpoError as exc:
            if exc.code not in _ACCOUNT_READ_RETRY_CODES or _timeout_remaining(deadline) <= 2.5:
                raise
            time.sleep(2)


def _timeout_remaining(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _validate_timeout(timeout_s: float) -> float:
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s) or timeout_s <= 0:
        _fail(
            "THS_TIMEOUT_INVALID",
            "timeout_s 必须是正数",
            "由调用方传入 GUI 配置中的有效等待上限",
            stage="timeout",
        )
    return float(timeout_s)


def _password_read(
    password_reader: Callable[[], str],
    *,
    ui: ThsUI,
    client: object,
    target: str,
) -> str:
    try:
        password = password_reader()
    except Exception as exc:
        code = exc.code if isinstance(exc, AutoIpoError) else "THS_PASSWORD_READ_FAILED"
        _fail(
            code,
            "读取同花顺登录密码失败",
            "检查 config/secrets.yaml 中该 username 的 DPAPI password_enc；不自动重试",
            ui=ui,
            client=client,
            target=target,
            stage="password_read",
        )
    if not isinstance(password, str) or not password:
        _fail(
            "THS_PASSWORD_READ_FAILED",
            "同花顺登录密码为空",
            "补录该 username 的 DPAPI password_enc 后再运行",
            ui=ui,
            client=client,
            target=target,
            stage="password_read",
        )
    return password


def _password_control_api(ui: ThsUI) -> PasswordControlUI | None:
    names = ("password_edit_controls", "password_control_filled", "set_password_control")
    found = [callable(getattr(ui, name, None)) for name in names]
    if not any(found):
        return None
    if not all(found):
        _fail(
            "THS_PASSWORD_CONTROL_API_INVALID",
            "密码控件最小接口不完整",
            "同时实现 password_edit_controls、password_control_filled、set_password_control",
            ui=ui,
            stage="password_control_api",
        )
    return ui  # type: ignore[return-value]


def _ensure_login_password(
    password_reader: Callable[[], str],
    *,
    ui: ThsUI,
    client: object,
    target: str,
) -> None:
    password_api = _password_control_api(ui)
    if password_api is None:
        if not ui.password_has_text():
            password = _password_read(password_reader, ui=ui, client=client, target=target)
            try:
                ui.set_password(password)
            except Exception as exc:
                if _is_stale_handle_error(exc):
                    _fail(
                        "THS_PASSWORD_CONTROL_HANDLE_STALE",
                        "填写密码框时控件句柄已失效",
                        "重新识别同花顺登录窗口后重试；不读取或输出 Edit 实际内容",
                        ui=ui,
                        client=client,
                        target=target,
                        stage="password_write",
                    )
                _fail(
                    "THS_PASSWORD_WRITE_FAILED",
                    "填写同花顺登录密码失败",
                    "检查登录窗口密码控件；不自动重试",
                    ui=ui,
                    client=client,
                    target=target,
                    stage="password_write",
                )
        return

    try:
        control = select_password_edit(password_api.password_edit_controls())
    except AutoIpoError as exc:
        context = dict(exc.context)
        context.update({"client": str(client or ""), "target": target, "stage": "password_control"})
        shot = _screenshot(ui, "password_control")
        if shot:
            context["screenshot"] = shot
        raise AutoIpoError(exc.code, exc.message, exc.hint, context) from None
    except Exception as exc:
        if _is_stale_handle_error(exc):
            _fail(
                "THS_PASSWORD_CONTROL_HANDLE_STALE",
                "读取密码框元数据时控件句柄已失效",
                "重新识别同花顺登录窗口后重试；不读取或输出 Edit 实际内容",
                ui=ui,
                client=client,
                target=target,
                stage="password_control",
            )
        _fail(
            "THS_PASSWORD_CONTROL_METADATA_INVALID",
            "读取登录窗口 Edit 控件元数据失败",
            "检查 control_id/style/rectangle；禁止读取或输出 Edit 内容",
            ui=ui,
            client=client,
            target=target,
            stage="password_control",
        )

    try:
        filled = password_api.password_control_filled(control)
    except Exception as exc:
        if _is_stale_handle_error(exc):
            _fail(
                "THS_PASSWORD_CONTROL_HANDLE_STALE",
                "读取密码框填充状态时控件句柄已失效",
                "重新识别同花顺登录窗口后重试；不读取或输出 Edit 实际内容",
                ui=ui,
                client=client,
                target=target,
                stage="password_state",
            )
        _fail(
            "THS_PASSWORD_STATE_READ_FAILED",
            "读取密码框是否已填失败",
            "只允许返回布尔填充状态；禁止读取或输出 Edit 实际内容",
            ui=ui,
            client=client,
            target=target,
            stage="password_state",
        )
    if filled:
        return

    password = _password_read(password_reader, ui=ui, client=client, target=target)
    try:
        password_api.set_password_control(control, password)
    except Exception as exc:
        if _is_stale_handle_error(exc):
            _fail(
                "THS_PASSWORD_CONTROL_HANDLE_STALE",
                "填写密码框时控件句柄已失效",
                "重新识别同花顺登录窗口后重试；不读取或输出 Edit 实际内容",
                ui=ui,
                client=client,
                target=target,
                stage="password_write",
            )
        _fail(
            "THS_PASSWORD_WRITE_FAILED",
            "填写同花顺登录密码失败",
            "检查已选密码框 control_id/style/rectangle；不自动重试",
            ui=ui,
            client=client,
            target=target,
            stage="password_write",
        )


def _switch_ths_account_unwrapped(
    target: ThsLoginAccount,
    client: object,
    password_reader: Callable[[], str],
    ui: ThsUI,
    timeout_s: float,
) -> ThsAccountSwitchResult:
    """切换并复核同花顺登录账户；密码最多读取和填写一次。"""
    timeout_s = _validate_timeout(timeout_s)
    target_name = _username(target)
    if not target_name:
        _fail(
            "THS_ACCOUNT_CONFIG_INVALID",
            "目标同花顺账户 username 不能为空",
            "传入客户端显示名 username",
            ui=ui,
            client=client,
            stage="target",
        )

    deadline = time.monotonic() + timeout_s
    login_ui = getattr(ui, "_switch_ui", None)
    if login_ui is None and callable(getattr(ui, "_delegate_ui", None)):
        login_ui = ui._delegate_ui()
    login_ui = login_ui or ui
    can_inspect_login_window = callable(getattr(login_ui, "_login_window", None))
    login_window_open = bool(
        can_inspect_login_window
        and _stage_call(
            "existing_login_window", ui.wait_for_login_window, min(5.0, _timeout_remaining(deadline)),
            ui=ui, client=client, target=target_name,
        )
    )
    if not login_window_open:
        if not _stage_call(
            "initial_main_window", ui.wait_for_main_window, _timeout_remaining(deadline),
            ui=ui, client=client, target=target_name,
        ):
            _fail(
                "THS_MAIN_WINDOW_TIMEOUT",
                "启动后等待同花顺主窗超时",
                "检查同花顺启动状态和 gui.ths_account_switch.restart_timeout_s",
                ui=ui, client=client, target=target_name,
                stage="initial_main_window",
            )
        current_name = _username(_stage_call(
            "current_account_name", _read_account_until_ready, ui.current_account_name, deadline,
            ui=ui, client=client, target=target_name,
        ))
        if current_name == target_name:
            return ThsAccountSwitchResult(username=target_name, status="reused")

        _stage_call(
            "close_main_window", ui.close_main_window,
            ui=ui, client=client, target=target_name,
        )
        if not _stage_call(
            "switch_popup", ui.wait_for_popup, _timeout_remaining(deadline),
            ui=ui, client=client, target=target_name,
        ):
            _fail(
                "THS_SWITCH_TIMEOUT",
                "等待关闭/切换账号弹窗超时",
                "检查同花顺窗口状态和 gui.ths_account_switch.dialog_wait_s",
                ui=ui, client=client, target=target_name,
                stage="switch_popup",
            )
        if _stage_call(
            "click_switch_account", ui.click_popup, SWITCH_ACCOUNT_ACTION,
            ui=ui, client=client, target=target_name,
        ) is False:
            _fail(
                "THS_UI_ACTION_FAILED",
                "点击“切换账号”失败",
                "查看失败截图并检查弹窗按钮文本",
                ui=ui, client=client, target=target_name,
                stage="click_switch_account",
            )
        if not _stage_call(
            "login_window", ui.wait_for_login_window, _timeout_remaining(deadline),
            ui=ui, client=client, target=target_name,
        ):
            _fail(
                "THS_LOGIN_WINDOW_TIMEOUT",
                "等待同花顺登录窗口超时",
                "检查客户端是否完成重启，必要时增大 login_wait_s",
                ui=ui, client=client, target=target_name,
                stage="login_window",
            )
    _stage_call(
        "account_dropdown", ui.open_account_dropdown,
        ui=ui, client=client, target=target_name,
    )
    names = [_username(item) for item in _stage_call(
        "account_dropdown_read", ui.account_display_names,
        ui=ui, client=client, target=target_name,
    )]
    matches = [name for name in names if name == target_name]
    if not matches:
        _fail(
            "THS_ACCOUNT_NOT_FOUND",
            f"登录窗口账号下拉找不到目标账户：{target_name}",
            "确认客户端已保存该显示名账户",
            ui=ui,
            client=client,
            target=target_name,
            stage="account_not_found",
        )
    if len(matches) > 1:
        _fail(
            "THS_ACCOUNT_AMBIGUOUS",
            f"登录窗口存在多个同名账户：{target_name}",
            "先在同花顺客户端清理重复显示名；不得按坐标盲选",
            ui=ui,
            client=client,
            target=target_name,
            stage="account_ambiguous",
        )
    _stage_call(
        "select_account", ui.select_account, matches[0],
        ui=ui, client=client, target=target_name,
    )

    _ensure_login_password(
        password_reader,
        ui=ui,
        client=client,
        target=target_name,
    )
    if _stage_call(
        "click_login", ui.click_login,
        ui=ui, client=client, target=target_name,
    ) is False:
        _fail(
            "THS_UI_ACTION_FAILED",
            "点击“登录”失败",
            "查看失败截图并检查登录按钮状态",
            ui=ui,
            client=client,
            target=target_name,
            stage="click_login",
        )
    if not _stage_call(
        "login_main_window", ui.wait_for_main_window, _timeout_remaining(deadline),
        ui=ui, client=client, target=target_name,
    ):
        _fail(
            "THS_LOGIN_TIMEOUT",
            "等待登录后主窗超时",
            "人工确认密码是否有效；程序不会循环尝试密码",
            ui=ui,
            client=client,
            target=target_name,
            stage="login_main_window",
        )

    actual_name = _username(_stage_call(
        "verify_account", _read_account_until_ready,
        lambda: _current_main_account_name(ui), deadline,
        ui=ui, client=client, target=target_name,
    ))
    if actual_name != target_name:
        _fail(
            "THS_ACCOUNT_VERIFY_FAILED",
            "登录后复核的 THS 账户名与目标不一致",
            "查看截图并人工确认当前客户端账户",
            ui=ui,
            client=client,
            target=target_name,
            stage="verify_account",
        )
    return ThsAccountSwitchResult(username=target_name, status="switched")


def switch_ths_account(
    target: ThsLoginAccount,
    client: object,
    password_reader: Callable[[], str],
    ui: ThsUI,
    timeout_s: float,
) -> ThsAccountSwitchResult:
    try:
        return _switch_ths_account_unwrapped(target, client, password_reader, ui, timeout_s)
    except AutoIpoError:
        raise
    except Exception as exc:
        if _is_stale_handle_error(exc):
            _fail(
                "THS_UI_HANDLE_STALE",
                "同花顺窗口控件句柄已失效",
                "重新识别同花顺窗口后重试；不读取或输出 Edit 实际内容",
                ui=ui,
                client=client,
                target=_username(target),
                stage="ui_stale_handle",
            )
        raise


def _close_ths_client_unwrapped(ui: ThsUI, timeout_s: float = 15.0) -> None:
    """等待关闭弹窗→精确点击“退出”→验证进程退出；禁止 taskkill 或强杀。"""
    timeout_s = _validate_timeout(timeout_s)
    deadline = time.monotonic() + timeout_s
    ui.close_main_window()
    if not ui.wait_for_popup(_timeout_remaining(deadline), EXIT_ACTION):
        _fail(
            "THS_CLIENT_EXIT_POPUP_TIMEOUT",
            "等待关闭/退出弹窗超时",
            "检查同花顺窗口状态和 gui.ths_account_switch.dialog_wait_s",
            ui=ui,
            stage="close_popup",
        )
    if ui.click_popup(EXIT_ACTION) is False:
        _fail(
            "THS_CLIENT_EXIT_FAILED",
            "点击关闭弹窗“退出”失败",
            "人工关闭同花顺客户端；系统不会强制结束进程",
            ui=ui,
            stage="close_exit",
        )
    if not ui.wait_for_client_exit(_timeout_remaining(deadline)):
        _fail(
            "THS_CLIENT_EXIT_TIMEOUT",
            "点击“退出”后同花顺进程未确认退出",
            "人工检查并关闭同花顺客户端；系统不会强制结束进程",
            ui=ui,
            stage="close_verify",
        )

def close_ths_client(ui: ThsUI, timeout_s: float = 15.0) -> None:
    try:
        _close_ths_client_unwrapped(ui, timeout_s)
    except AutoIpoError:
        raise
    except Exception as exc:
        if _is_stale_handle_error(exc):
            _fail(
                "THS_UI_HANDLE_STALE",
                "关闭同花顺时窗口控件句柄已失效",
                "重新识别同花顺窗口后重试；系统不会强制结束进程",
                ui=ui,
                stage="close_ui_stale_handle",
            )
        raise
