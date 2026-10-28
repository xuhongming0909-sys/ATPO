# AI-SUMMARY: 同花顺 Win32 窗口适配——命令行只读识别、OCR 兜底和密码/账户控件操作
from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from execution.client_registry import ClientSpec
from execution.ths_account_model import (
    FundAccountLoginResult,
    FundAccountRef,
    _USERNAME_TOKEN,
    _norm,
    match_fund_account,
)
from execution.ths_account_switch import SWITCH_ACCOUNT_ACTION
from shared.errors import AutoIpoError

WM_CLOSE = 0x0010

def _command_lines_for_pids(pids: set[int]) -> list[str]:
    """只读查询精确 PID 的命令行原文；调用方只做已知 username 边界匹配，不回显原文。"""
    wanted = set()
    for pid in pids or set():
        try:
            if int(pid) > 0:
                wanted.add(int(pid))
        except Exception:
            continue
    if not wanted:
        return []
    try:
        import win32com.client

        locator = win32com.client.GetObject("winmgmts:")
        rows = locator.ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process")
        out = []
        for row in rows:
            try:
                if int(row.ProcessId) in wanted and row.CommandLine:
                    out.append(str(row.CommandLine))
            except Exception:
                continue
        return out
    except Exception:
        return []

def _default_username_ocr(window: Any, usernames: Sequence[str], settings: Mapping[str, Any]) -> str:
    """截取主窗右上自绘区域，调用 64 位 OCR helper；只返回已知 username。"""
    import json
    import shutil
    import subprocess
    import uuid
    from PIL import ImageGrab
    from shared.paths import PROJECT_ROOT, runtime_path

    rect = window.rectangle()
    if isinstance(rect, (tuple, list)):
        left, top, right, bottom = map(int, rect)
    else:
        left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    width = max(1, right - left)
    x_ratio = max(0.0, min(0.95, float(settings.get("username_ocr_x_ratio", 0.65))))
    top_px = max(24, min(100, int(settings.get("username_ocr_top_px", 36))))
    box = (left + int(width * x_ratio), top, right, min(bottom, top + top_px))
    image_dir = runtime_path("ocr")
    image_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / f"{uuid.uuid4().hex}.png"
    # 截图前把主窗置前，避免截到遮挡窗口像素导致 OCR 误判
    try:
        import win32gui

        handle = int(getattr(window, "handle", 0) or 0)
        if handle:
            win32gui.ShowWindow(handle, 9)
            win32gui.SetForegroundWindow(handle)
            time.sleep(0.5)
    except Exception:
        pass
    matched = False
    try:
        ImageGrab.grab(bbox=box).save(image_path)
        payload = {
            "usernames": list(usernames),
            "min_score": float(settings.get("username_ocr_min_score", 0.78)),
            "min_margin": float(settings.get("username_ocr_min_margin", 0.12)),
        }
        from shared.username_ocr import serve_request

        result = serve_request(image_path, "match", payload, timeout_s=20)
        if result is None:
            py = shutil.which("py")
            command = [py, "-3.12"] if py else [shutil.which("python") or "python"]
            command += [str(PROJECT_ROOT / "shared" / "username_ocr.py"), "--image", str(image_path)]
            proc = subprocess.run(
                command,
                input=json.dumps(payload, ensure_ascii=True),
                text=True,
                capture_output=True,
                timeout=20,
                cwd=str(PROJECT_ROOT),
            )
            result = json.loads(proc.stdout or "{}")
        if result.get("status") != "matched":
            raise AutoIpoError(
                "THS_CURRENT_ACCOUNT_OCR_UNMATCHED",
                "OCR 无法唯一识别当前同花顺 username",
                "确认右上角显示目标账户名，或检查 64 位 OCR 依赖",
                {"status": result.get("status", "error")},
            )
        matched = True
        return str(result.get("username") or "")
    except AutoIpoError:
        raise
    except Exception:
        raise AutoIpoError(
            "THS_CURRENT_ACCOUNT_OCR_FAILED",
            "同花顺 username OCR 调用失败",
            "运行 python run.py doctor 检查 64 位 OCR 依赖",
        ) from None
    finally:
        if matched:
            try:
                image_path.unlink(missing_ok=True)
            except Exception:
                pass

def _window_main_sized(window) -> bool:
    """主窗尺寸下限：兼容 RECT 对象与 (l,t,r,b) 元组；启动小窗/弹窗不算主窗。"""
    try:
        rect = window.rectangle()
        if isinstance(rect, (tuple, list)):
            left, top, right, bottom = (int(v) for v in rect[:4])
        else:
            left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
        return (right - left) >= 800 and (bottom - top) >= 500
    except Exception:
        return False


class HexinSwitchUI:
    """ThsUI 的 Win32/pywinauto 实现；控件按文本/已知显示名动态定位。"""

    def __init__(
        self,
        client: ClientSpec,
        cfg: Mapping[str, Any],
        *,
        known_ths_accounts: Sequence[str] = (),
        command_line_fn: Callable[[set[int]], Sequence[str]] | None = None,
        visible_texts_fn: Callable[[Any], Sequence[str]] | None = None,
        username_ocr_fn: Callable[[Any, Sequence[str], Mapping[str, Any]], str] | None = None,
        screenshot_fn: Callable[[str], object] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self.client = client
        self.cfg = dict(cfg or {})
        self.known_ths_accounts = tuple(str(v).strip() for v in known_ths_accounts if str(v).strip())
        self._command_line_fn = command_line_fn or _command_lines_for_pids
        self._visible_texts_fn = visible_texts_fn
        self._username_ocr_fn = username_ocr_fn or _default_username_ocr
        self._screenshot_fn = screenshot_fn
        self._sleep = sleep_fn

    def _settings(self) -> dict:
        return dict((self.cfg.get("gui") or {}).get("ths_account_switch") or {})

    def _pids(self) -> set[int]:
        from execution.hexin_login import _hexin_pids

        return set(_hexin_pids(self.client))

    def _windows(self, visible_only: bool = True) -> list[Any]:
        from pywinauto import Desktop

        pids = self._pids()
        result = []
        windows = []
        for _attempt in range(2):
            try:
                windows = list(Desktop(backend="win32").windows())
                break
            except Exception:
                continue
        for window in windows:
            try:
                if int(window.process_id()) not in pids:
                    continue
                if visible_only and not window.is_visible():
                    continue
                result.append(window)
            except Exception:
                continue
        return result

    def _texts(self, window: Any) -> list[str]:
        values = []
        try:
            if window.window_text():
                values.append(str(window.window_text()))
        except Exception:
            pass
        try:
            controls = list(window.descendants())
        except Exception:
            controls = []
            for control_name in ("Static", "Edit", "Button", "ComboBox"):
                try:
                    controls.extend(window.descendants(class_name=control_name))
                except Exception:
                    continue
        for control in controls:
            try:
                text = str(control.window_text() or "").strip()
                if text:
                    values.append(text)
            except Exception:
                pass
            try:
                values.extend(str(v or "").strip() for v in control.item_texts())
            except Exception:
                continue
        return [value for value in values if value]

    def _known_names_in(self, texts: Sequence[str]) -> list[str]:
        found = []
        for name in self.known_ths_accounts:
            pattern = re.compile(
                r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", re.I
            )
            if any(pattern.search(str(text or "")) for text in texts):
                found.append(name)
        return list(dict.fromkeys(found))

    def _command_line_texts(self) -> list[str]:
        try:
            pids = self._pids()
        except Exception:
            pids = set()
        try:
            return [str(value or "") for value in (self._command_line_fn(pids) or [])]
        except Exception:
            return []


    def current_account_name(self) -> str:
        for attempt in range(2):
            try:
                return self._read_current_account_name()
            except AutoIpoError:
                if attempt:
                    raise
            except Exception:
                if attempt:
                    raise AutoIpoError(
                        "THS_CURRENT_ACCOUNT_UNREADABLE",
                        "同花顺主窗句柄失效，重新枚举后仍无法读取当前账户",
                        "确认同花顺主窗保持打开后重试",
                        {"read_attempts": 2},
                    ) from None
        raise AutoIpoError(
            "THS_CURRENT_ACCOUNT_UNREADABLE",
            "无法安全读取当前同花顺账户",
            "确认同花顺主窗保持打开后重试",
            {"read_attempts": 2},
        )

    def _selected_login_username(self) -> str:
        try:
            window = self._login_window()
            if window is None:
                return ""
            combo = self._login_combo()
            text = str(combo.window_text() or "").strip()
        except Exception:
            return ""
        known = self._known_names_in([text])
        if len(known) == 1:
            return known[0]
        tokens = sorted({match.group(0) for match in _USERNAME_TOKEN.finditer(text)})
        return tokens[0] if len(tokens) == 1 else ""
    def _read_current_account_name(self, *, allow_login_selection: bool = True) -> str:
        if allow_login_selection:
            selected = self._selected_login_username()
            if selected:
                return selected
        visible: list[str] = []
        for window in self._windows():
            if self._visible_texts_fn is not None:
                visible.extend(str(value or "") for value in self._visible_texts_fn(window))
            else:
                visible.extend(self._texts(window))
        known = self._known_names_in(visible)
        if len(known) == 1:
            return known[0]
        if len(known) > 1:
            raise AutoIpoError(
                "THS_CURRENT_ACCOUNT_UNREADABLE",
                "同花顺可见文本存在多个已知 username，无法安全确定当前账户",
                "确认主界面只显示一个目标账户名，或注入 current_account_name_fn",
                {"known_matches": len(known)},
            )
        tokens = sorted({
            match.group(0)
            for text in visible
            for match in _USERNAME_TOKEN.finditer(str(text or ""))
        })
        if len(tokens) == 1:
            return tokens[0]
        if len(tokens) > 1:
            raise AutoIpoError(
                "THS_CURRENT_ACCOUNT_UNREADABLE",
                "同花顺可见文本存在多个 username 候选，无法安全确定当前账户",
                "确认主界面只显示一个目标账户名，或注入 current_account_name_fn",
                {"visible_matches": len(tokens)},
            )
        known = self._known_names_in(self._command_line_texts())
        if len(known) == 1:
            return known[0]
        if self.known_ths_accounts:
            try:
                windows = [window for window in self._windows()
                           if _norm("同花顺") in _norm(window.window_text()) and _window_main_sized(window)]
                if len(windows) == 1:
                    username = str(self._username_ocr_fn(windows[0], self.known_ths_accounts, self._settings()) or "").strip()
                    if username in self.known_ths_accounts:
                        return username
            except AutoIpoError:
                raise
            except Exception:
                pass
        raise AutoIpoError(
            "THS_CURRENT_ACCOUNT_UNREADABLE",
            "无法从同花顺主界面可见文本或进程命令行安全解析当前 username",
            "确认主界面显示目标账户名，或注入 current_account_name_fn",
            {
                "visible_texts_checked": len(visible),
                "known_accounts": len(self.known_ths_accounts),
                "known_matches": len(known),
            },
        )

    def current_main_account_name(self) -> str:
        if self._main_window() is None:
            return ""
        return self._read_current_account_name(allow_login_selection=False)

    def close_main_window(self) -> None:
        windows = self._windows()
        wanted = _norm(self._settings().get("main_window_title") or "同花顺")
        candidates = []
        for window in windows:
            try:
                title = _norm(window.window_text())
                class_name = str(window.class_name() or "")
                if class_name == "#32770":
                    continue
                if wanted and title and wanted not in title:
                    continue
                if not title and not _window_main_sized(window):
                    continue
                candidates.append(window)
            except Exception:
                continue
        if len(candidates) != 1:
            raise AutoIpoError(
                "THS_MAIN_WINDOW_NOT_UNIQUE",
                f"同花顺主窗无法唯一识别（匹配到 {len(candidates)} 个）",
                "关闭重复主窗或配置 gui.ths_account_switch.main_window_title；禁止关闭同 PID 全部窗口",
                {"count": len(candidates)},
            )
        window = candidates[0]
        handle = int(getattr(window, "handle", 0) or 0)
        if handle:
            import win32gui

            try:
                win32gui.PostMessage(handle, WM_CLOSE, 0, 0)  # 非阻塞；退出弹窗由 close 流程精确点击
            except Exception:
                pass
            return
        try:
            window.close()
        except Exception:
            pass

    @staticmethod
    def _action_key(action: str) -> str:
        return {
            "切换账号": "switch_account",
            "退出": "exit",
            "取消": "cancel",
        }.get(action, _norm(action))

    def _button(self, window: Any, action: str) -> Any | None:
        wanted = _norm(self._settings().get(f"{action}_text") or action)
        key = self._action_key(action)
        control_id = self._settings().get(f"{key}_control_id")
        try:
            buttons = list(window.descendants(class_name="Button"))
        except Exception:
            return None
        for button in buttons:
            try:
                if control_id is not None and int(button.control_id()) == int(control_id):
                    return button
                if self._action_text_matches(button.window_text(), wanted):
                    return button
            except Exception:
                continue
        return None

    @staticmethod
    def _action_text_matches(text: str, wanted: str) -> bool:
        value = _norm(text)
        if value == wanted:
            return True
        return re.sub(r"\(&[a-z0-9]\)$", "", value) == wanted

    def _popup_window(self, action: str = "") -> Any | None:
        for window in self._windows():
            try:
                if not action or self._button(window, action) is not None:
                    return window
            except Exception:
                continue
        return None

    def wait_for_popup(self, timeout_s: float, action: str = SWITCH_ACCOUNT_ACTION) -> bool:
        wanted = action or SWITCH_ACCOUNT_ACTION
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while True:
            if self._popup_window(wanted) is not None:
                return True
            if time.monotonic() >= deadline:
                return False
            self._sleep(0.2)

    def _client_process_pids(self) -> set[int]:
        from execution.client_lifecycle import find_processes

        xiadan = Path(self.client.xiadan_path)
        paths = [
            self.client.hexin_path,
            xiadan,
            xiadan.parent / "xiadan-plus" / "xiadan-plus.exe",
        ]
        found = find_processes(paths)
        return {int(pid) for pids in found.values() for pid in pids}

    def wait_for_client_exit(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while True:
            if not self._pids():
                return True
            if time.monotonic() >= deadline:
                return False
            self._sleep(0.2)

    def click_popup(self, action: str) -> bool:
        window = self._popup_window(action)
        button = self._button(window, action) if window is not None else None
        if button is None:
            return False
        return self._click_button(button)

    @staticmethod
    def _control_rectangle(button: Any) -> tuple[int, int, int, int] | None:
        getter = getattr(button, "rectangle", None)
        if not callable(getter):
            return None
        try:
            rect = getter()
            if isinstance(rect, (tuple, list)) and len(rect) >= 4:
                left, top, right, bottom = map(int, rect[:4])
            else:
                left, top, right, bottom = (
                    int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
                )
        except Exception:
            return None
        return left, top, right, bottom

    def _login_window_open(self, window: Any) -> bool:
        if self._window_visible(window):
            return True
        try:
            return self._login_window() is not None
        except Exception:
            return False

    def _send_button_click(self, button: Any) -> bool:
        handle = int(getattr(getattr(button, "element_info", None), "handle", 0) or getattr(button, "handle", 0) or 0)
        if not handle:
            return False
        try:
            import win32gui

            win32gui.SendMessage(handle, 0x00F5, 0, 0)  # BM_CLICK
            return True
        except Exception:
            return False

    def _press_login_enter(self, window: Any) -> bool:
        try:
            window.type_keys("{ENTER}")
            return True
        except Exception:
            pass
        handle = int(getattr(window, "handle", 0) or 0)
        if not handle:
            return False
        try:
            import win32con
            import win32gui

            win32gui.PostMessage(handle, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
            win32gui.PostMessage(handle, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
            return True
        except Exception:
            return False

    @staticmethod
    def _window_visible(window: Any) -> bool:
        handle = int(getattr(window, "handle", 0) or 0)
        if not handle:
            return True
        try:
            import win32gui

            return bool(win32gui.IsWindowVisible(handle))
        except Exception:
            return True

    def _click_screen(self, button: Any) -> bool:
        """Fallback to a physical click for custom-drawn login buttons."""
        rect = self._control_rectangle(button)
        if rect is None:
            return False
        left, top, right, bottom = rect
        try:
            import win32api
            import win32con

            point = ((left + right) // 2, (top + bottom) // 2)
            win32api.SetCursorPos(point)
            self._sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0)
            self._sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0)
            return True
        except Exception:
            return False

    def _click_button(self, button: Any) -> bool:
        click_input = getattr(button, "click_input", None)
        if callable(click_input):
            try:
                click_input()
                return True
            except Exception:
                pass
        try:
            button.click()
            return True
        except Exception:
            pass
        return False

    def _login_window(self) -> Any | None:
        title = str(self._settings().get("login_window_title") or "")
        for window in self._windows():
            try:
                if title and title not in str(window.window_text() or ""):
                    continue
                edits = list(window.descendants(class_name="Edit"))
                combos = list(window.descendants(class_name="ComboBox"))
                buttons = [str(b.window_text() or "") for b in window.descendants(class_name="Button")]
                if edits and combos and any(_norm(v) == _norm(self._settings().get("login_button_text") or "登录") for v in buttons):
                    return window
            except Exception:
                continue
        return None

    def _main_window(self) -> Any | None:
        title = str(self._settings().get("main_window_title") or "同花顺")
        for window in self._windows():
            try:
                text = str(window.window_text() or "")
                if title and text and title not in text:
                    continue
                if "登录" in text:
                    continue
                if not _window_main_sized(window):
                    continue  # 启动小窗/弹窗不算主窗
                return window
            except Exception:
                continue
        return None

    def wait_for_login_window(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while time.monotonic() < deadline:
            self._dismiss_startup_errors()
            if self._login_window() is not None:
                return True
            self._sleep(0.2)
        return False

    def _login_combo(self) -> Any:
        window = self._login_window()
        if window is None:
            raise AutoIpoError("THS_LOGIN_WINDOW_MISSING", "未找到同花顺登录窗口", "检查切换账号流程")
        wanted = {_norm(name) for name in self.known_ths_accounts}
        candidates = []
        for combo in window.descendants(class_name="ComboBox"):
            try:
                names = [str(v or "").strip() for v in combo.item_texts()]
                if wanted & {_norm(name) for name in names}:
                    candidates.append(combo)
            except Exception:
                continue
        if len(candidates) != 1:
            raise AutoIpoError(
                "THS_LOGIN_ACCOUNT_COMBO_NOT_UNIQUE",
                f"登录窗口账号下拉匹配到 {len(candidates)} 个 ComboBox",
                "确保 username 显示名唯一且登录窗口未重复",
                {"count": len(candidates)},
            )
        return candidates[0]

    @staticmethod
    def _combo_handle(combo: Any) -> int:
        value = getattr(combo, "handle", 0)
        if callable(value):
            try:
                value = value()
            except Exception:
                value = 0
        if not value:
            value = getattr(getattr(combo, "element_info", None), "handle", 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def open_account_dropdown(self) -> None:
        combo = self._login_combo()
        handle = self._combo_handle(combo)
        if handle:
            import win32gui

            win32gui.SendMessage(handle, 0x014F, 1, 0)  # CB_SHOWDROPDOWN
            return
        expand = getattr(combo, "expand", None)
        if callable(expand):
            expand()
            return
        click_input = getattr(combo, "click_input", None)
        if callable(click_input):
            click_input()
            return
        combo.click()

    def account_display_names(self) -> Sequence[str]:
        return [str(value or "").strip() for value in self._login_combo().item_texts()
                if str(value or "").strip()]

    def select_account(self, username: str) -> None:
        combo = self._login_combo()
        names = [str(value or "").strip() for value in combo.item_texts()]
        try:
            index = names.index(str(username or "").strip())
        except ValueError:
            raise AutoIpoError(
                "THS_ACCOUNT_NOT_FOUND",
                "登录窗口账号下拉找不到目标账户",
                "确认客户端已保存该 username",
                {"username": str(username or "")},
            ) from None
        handle = self._combo_handle(combo)
        if handle:
            import win32gui

            win32gui.SendMessage(handle, 0x014E, index, 0)  # CB_SETCURSEL
            win32gui.SendMessage(handle, 0x014F, 0, 0)      # CB_SHOWDROPDOWN
            return
        combo.select(username)

    @staticmethod
    def _edit_handle(edit: Any) -> int:
        value = getattr(edit, "handle", 0)
        if callable(value):
            try:
                value = value()
            except Exception:
                value = 0
        if not value:
            value = getattr(getattr(edit, "element_info", None), "handle", 0)
        if callable(value):
            try:
                value = value()
            except Exception:
                value = 0
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

    @staticmethod
    def _password_hint_value(control: Any) -> bool:
        candidates = (
            getattr(control, "is_password", None),
            getattr(getattr(control, "element_info", None), "is_password", None),
        )
        for value in candidates:
            if callable(value):
                try:
                    value = value()
                except Exception:
                    continue
            if isinstance(value, bool):
                return value
        return False

    @staticmethod
    def _write_password_control_diagnostics(
        valid_rows: Sequence[Mapping[str, Any]],
        invalid_rows: Sequence[Mapping[str, Any]],
    ) -> None:
        import json
        from shared.paths import runtime_path

        path = runtime_path("diagnostics", "password_edit_metadata.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "valid_rows": [dict(row) for row in valid_rows],
            "invalid_rows": [dict(row) for row in invalid_rows],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )
    def _password_control_rows(self) -> list[tuple[Any, dict[str, Any]]]:
        """读取 Edit 稳定元数据；只判断填充状态，绝不读取输入内容。"""
        window = self._login_window()
        if window is None:
            raise AutoIpoError("THS_LOGIN_WINDOW_MISSING", "未找到同花顺登录窗口", "检查切换账号流程")
        import win32gui

        rows: list[tuple[Any, dict[str, Any]]] = []
        valid_diagnostics: list[dict[str, Any]] = []
        invalid_diagnostics: list[dict[str, Any]] = []
        for index, edit in enumerate(window.descendants(class_name="Edit")):
            stage = "visible"
            try:
                visible = bool(edit.is_visible())
                stage = "handle"
                handle = self._edit_handle(edit)
                stage = "control_id"
                control_id = self._control_id_value(edit)
                if control_id < 0 and handle:
                    control_id = int(win32gui.GetDlgCtrlID(handle))
                stage = "style"
                password_hint = self._password_hint_value(edit)
                style_value = getattr(edit, "style", None)
                if callable(style_value):
                    style_value = style_value()
                if style_value is None:
                    style_value = getattr(getattr(edit, "element_info", None), "style", None)
                    if callable(style_value):
                        style_value = style_value()
                if style_value is None and handle:
                    style_value = win32gui.GetWindowLongW(handle, -16)
                style = int(style_value) if style_value is not None else (
                    0x0020 if password_hint else 0
                )
                stage = "rectangle"
                rect = edit.rectangle()
                rectangle = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
                meta = {
                    "control_id": max(0, control_id),
                    "style": style,
                    "rectangle": rectangle,
                    "visible": visible,
                    "password_hint": password_hint,
                }
                rows.append((edit, meta))
                valid_diagnostics.append({"index": index, **meta})
            except Exception as exc:
                invalid_diagnostics.append({
                    "index": index,
                    "stage": stage,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })
                continue
        self._write_password_control_diagnostics(valid_diagnostics, invalid_diagnostics)
        if not rows and invalid_diagnostics:
            raise AutoIpoError(
                "THS_PASSWORD_CONTROL_METADATA_INVALID",
                "读取登录窗口 Edit 控件元数据失败",
                "检查 style/password_hint/rectangle；control_id 和 handle 可缺失；禁止读取或输出 Edit 内容",
                {
                    "invalid_edit_count": len(invalid_diagnostics),
                    "diagnostic": "runtime_data/diagnostics/password_edit_metadata.json",
                },
            ) from None
        return rows

    def password_edit_controls(self) -> Sequence[Mapping[str, Any]]:
        return [dict(meta) for _edit, meta in self._password_control_rows()]

    def _password_edit(self, control: Any | None = None) -> Any:
        from execution.ths_account_switch import select_password_edit

        rows = self._password_control_rows()
        if control is None:
            control = select_password_edit([meta for _edit, meta in rows])
        wanted_id = int(getattr(control, "control_id", 0))
        wanted_rect = tuple(getattr(control, "rectangle", ()))
        matched = [
            edit for edit, meta in rows
            if meta["visible"] and int(meta["control_id"]) == wanted_id
            and tuple(meta["rectangle"]) == wanted_rect
            and int(meta["style"]) == int(getattr(control, "style", meta["style"]))
            and bool(meta["password_hint"]) == bool(getattr(control, "password_hint", meta["password_hint"]))
        ]
        if len(matched) != 1:
            raise AutoIpoError(
                "THS_PASSWORD_CONTROL_NOT_UNIQUE",
                "密码框稳定元数据无法唯一定位",
                "检查登录窗口 Edit 的 control_id/style/rectangle",
                {"count": len(matched)},
            )
        return matched[0]

    def password_control_filled(self, control: Any) -> bool:
        import win32gui

        edit = self._password_edit(control)
        handle = self._edit_handle(edit)
        if bool(handle):
            if win32gui.GetWindowTextLength(handle) > 0:
                return True
            send_message = getattr(win32gui, "SendMessage", None)
            if callable(send_message) and int(send_message(handle, 0x00C1, 0, 0)) > 0:
                return True
        return self._saved_password_checkbox_checked()

    def _saved_password_checkbox_checked(self) -> bool:
        window = self._login_window()
        if window is None:
            return False
        wanted = _norm(self._settings().get("saved_password_checkbox_text") or "保存密码")
        try:
            buttons = list(window.descendants(class_name="Button"))
        except Exception:
            buttons = list(window.descendants())
        for button in buttons:
            try:
                if _norm(button.window_text()) != wanted:
                    continue
                getter = getattr(button, "get_toggle_state", None)
                if callable(getter) and int(getter()) == 1:
                    return True
                checker = getattr(button, "is_checked", None)
                if callable(checker) and bool(checker()):
                    return True
                import win32gui
                handle = getattr(getattr(button, "element_info", None), "handle", 0)
                if handle and int(win32gui.SendMessage(handle, 0x00F0, 0, 0)) in (1, 2):
                    return True
            except Exception:
                continue
        return False

    def set_password_control(self, control: Any, password: str) -> None:
        try:
            self._password_edit(control).set_edit_text(password)
        except Exception:
            raise AutoIpoError(
                "THS_PASSWORD_WRITE_FAILED",
                "填写同花顺登录密码失败",
                "检查已选密码框 control_id/style/rectangle；不自动重试",
            ) from None

    def password_has_text(self) -> bool:
        from execution.ths_account_switch import select_password_edit

        return self.password_control_filled(select_password_edit(self.password_edit_controls()))

    def set_password(self, password: str) -> None:
        from execution.ths_account_switch import select_password_edit

        self.set_password_control(select_password_edit(self.password_edit_controls()), password)

    def click_login(self) -> bool:
        window = self._login_window()
        button = self._button(window, self._settings().get("login_button_text") or "登录") if window else None
        if button is None:
            return False
        attempted = self._click_button(button)
        rect = self._control_rectangle(button)
        verify_wait = float(self._settings().get("login_click_verify_wait_s", 0.5))
        if verify_wait > 0:
            self._sleep(verify_wait)
        if not self._login_window_open(window):
            return True
        attempted = self._send_button_click(button) or attempted
        self._sleep(verify_wait)
        if not self._login_window_open(window):
            return True
        if rect is not None:
            try:
                attempted = self._click_screen(button) or attempted
            except Exception:
                pass
            self._sleep(verify_wait)
        if self._login_window_open(window):
            attempted = self._press_login_enter(window) or attempted
        if self._login_window_open(window):
            try:
                from execution.captcha_login import try_captcha_login

                if try_captcha_login(self._pids()):
                    self._sleep(0.5)
                    return not self._login_window_open(window)
            except Exception:
                pass
        return bool(attempted)

    def _dismiss_startup_errors(self) -> bool:
        try:
            windows = self._windows()
        except Exception:
            return False
        for window in windows:
            try:
                texts = [str(window.window_text() or "")]
                texts.extend(str(item.window_text() or "") for item in window.descendants())
                if not any("未知错误" in text for text in texts):
                    continue
                for button in window.descendants(class_name="Button"):
                    if str(button.window_text() or "") != "确定":
                        continue
                    handle = int(getattr(getattr(button, "element_info", None), "handle", 0)
                                 or getattr(button, "handle", 0) or 0)
                    if not handle:
                        continue
                    import win32con
                    import win32gui

                    win32gui.SendMessage(handle, win32con.BM_CLICK, 0, 0)
                    return True
            except Exception:
                continue
        return False

    def wait_for_main_window(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while time.monotonic() < deadline:
            self._dismiss_startup_errors()
            try:
                found = self._main_window()
            except Exception:
                found = None
            if found is not None:
                return True
            self._sleep(0.2)
        return False

    def save_screenshot(self, name: str) -> object:
        if self._screenshot_fn is None:
            return ""
        return self._screenshot_fn(name)

