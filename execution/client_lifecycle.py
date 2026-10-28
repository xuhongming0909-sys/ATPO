# AI-SUMMARY: 同花顺客户端任务生命周期——精确 exe/PID 归属、温和关闭和开始/关闭留痕
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

from execution.client_registry import ClientSpec
from shared.errors import AutoIpoError
from shared.paths import ensure_runtime_dirs, runtime_path

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
WM_CLOSE = 0x0010


@dataclass
class ProcessRecord:
    role: str
    path: str
    pids: list[int]
    origin: str = "preexisting"
    start_status: str = "present"
    close_status: str = "not_started"
    error_code: str = ""
    error: str = ""


@dataclass
class ClientLifecycleRecord:
    client_id: str
    operation: str
    started_at: str
    closed_at: str = ""
    processes: list[ProcessRecord] = field(default_factory=list)
    status: str = "running"
    error_code: str = ""
    error: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _normalize(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _query_image_path_wmi(pid: int) -> str:
    """OpenProcess 被拒绝时只读查询精确 PID 的 ExecutablePath，不读取命令行。"""
    try:
        import win32com.client

        locator = win32com.client.GetObject("winmgmts:")
        rows = locator.ExecQuery(
            f"SELECT ExecutablePath FROM Win32_Process WHERE ProcessId={int(pid)}"
        )
        for row in rows:
            return str(row.ExecutablePath or "")
    except Exception:
        return ""
    return ""


def _image_path(pid: int) -> str:
    process = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return _query_image_path_wmi(pid)
    try:
        size = ctypes.c_uint32(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size))
        return buffer.value if ok else _query_image_path_wmi(pid)
    finally:
        ctypes.windll.kernel32.CloseHandle(process)


def _pid_active(pid: int) -> bool:
    process = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return False
    try:
        code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(process, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        ctypes.windll.kernel32.CloseHandle(process)


def find_processes(paths: list[Path], image_path_fn: Callable[[int], str] | None = None) -> dict[str, list[int]]:
    """只返回可验证为指定绝对 exe 的 PID；同名其他目录进程绝不归属。"""
    lookup = image_path_fn or _image_path
    output = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    pids: list[int] = []
    for line in output.stdout.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            pids.append(int(parts[1]))
    if not pids:
        powershell = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "Get-Process | Select-Object Id | ConvertTo-Json -Compress"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        try:
            import json

            rows = json.loads(powershell.stdout or "[]")
            if isinstance(rows, dict):
                rows = [rows]
            pids = [int(row["Id"]) for row in rows if str(row.get("Id", "")).isdigit()]
        except Exception:
            pids = []
    wanted = {_normalize(path): str(path) for path in paths}
    found = {str(path): [] for path in paths}
    for pid in pids:
        image = lookup(pid)
        if not image:
            continue
        original = wanted.get(_normalize(image))
        if original:
            found[original].append(pid)
    return found


def _start(path: Path, baseline: set[int], _popen: Callable | None = None) -> int:
    if not path.is_file():
        raise AutoIpoError(
            "CLIENT_EXE_MISSING",
            f"客户端程序不存在：{path}",
            "修正 config/config.yaml → execution.clients 的 exe 路径",
            {"path": str(path)},
        )
    popen = _popen or subprocess.Popen
    try:
        proc = popen([str(path)], cwd=str(path.parent))
    except Exception as exc:
        raise AutoIpoError(
            "CLIENT_START_FAILED",
            f"客户端启动失败：{path.name}",
            "确认本机已安装同花顺且当前用户有权运行该程序",
            {"path": str(path), "error": str(exc)[:150]},
        ) from exc
    deadline = time.time() + 5
    while time.time() < deadline:
        current = find_processes([path]).get(str(path), [])
        fresh = [pid for pid in current if pid not in baseline]
        if fresh:
            return fresh[0]
        time.sleep(0.2)
    return 0


def _window_pids(pid: int) -> list[int]:
    import win32gui
    import win32process

    result: list[int] = []
    def collect(hwnd, _):
        try:
            _, found = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return
        if int(found) == int(pid):
            result.append(hwnd)
    win32gui.EnumWindows(collect, None)
    return result


def _taskkill_close(pid: int, timeout_s: float) -> tuple[bool, str]:
    """最后温和信号：taskkill 只发关闭请求，绝不使用 /F。"""
    command = ["taskkill", "/PID", str(int(pid))]
    if any(str(part).lower() == "/f" for part in command):
        raise AssertionError("taskkill 禁止使用 /F")
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1.0, timeout_s),
            check=False,
        )
    except Exception as exc:
        return False, f"taskkill 温和关闭失败：{str(exc)[:100]}"
    if result.returncode == 0:
        return True, ""
    return False, f"taskkill 温和关闭失败 exit={result.returncode}"


def confirm_exit_dialogs(pids: set[int]) -> int:
    """同花顺退出确认框（自绘按钮无文本）：识别 切换账号(20199)+取消(20149)+退出(21042)

    组合后只点「退出」。2026-10-24 实战：hexin 的 WM_CLOSE 会弹该广告确认框，
    无人点退出则进程永不退出。绝不点切换账号/取消。
    """
    import win32api
    import win32con
    import win32gui
    import win32process

    clicked = 0

    def on_window(hwnd, _):
        nonlocal clicked
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if int(pid) not in pids or not win32gui.IsWindowVisible(hwnd):
                return
            control_ids = set()

            def collect(child, _):
                try:
                    control_ids.add(int(win32gui.GetDlgCtrlID(child)))
                except Exception:
                    pass

            win32gui.EnumChildWindows(hwnd, collect, None)
            if not {20199, 20149, 21042}.issubset(control_ids):
                return
            button = win32gui.GetDlgItem(hwnd, 21042)
            if not button:
                return
            rect = win32gui.GetWindowRect(button)
            center = ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)
            previous = win32api.GetCursorPos()
            try:
                win32api.SetCursorPos(center)
                time.sleep(0.05)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                time.sleep(0.03)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            finally:
                try:
                    win32api.SetCursorPos(previous)
                except Exception:
                    pass
            clicked += 1
        except Exception:
            pass

    try:
        win32gui.EnumWindows(on_window, None)
    except Exception:
        pass
    return clicked


def _close_pid(pid: int, timeout_s: float, _wait_pid: Callable[[int, float], bool] | None = None,
               _on_wait: Callable[[], None] | None = None) -> tuple[bool, str]:
    if not _pid_active(pid):
        return True, ""
    try:
        import win32gui
        for hwnd in _window_pids(pid):
            try:
                win32gui.PostMessage(hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass
    except Exception as exc:
        return False, f"发送 WM_CLOSE 失败：{str(exc)[:100]}"
    wait = _wait_pid or _wait_exit
    if _on_wait is not None:
        deadline = time.time() + timeout_s
        while time.time() < deadline and _pid_active(pid):
            try:
                _on_wait()
            except Exception:
                pass
            time.sleep(0.5)
        if not _pid_active(pid):
            return True, ""
    elif wait(pid, timeout_s):
        return True, ""
    task_ok, task_error = _taskkill_close(pid, timeout_s)
    if wait(pid, timeout_s):
        return True, ""
    if task_ok:
        return False, f"PID {pid} 在 {timeout_s:g}s 内未退出"
    return False, f"PID {pid} 在 {timeout_s:g}s 内未退出；{task_error}"



def _wait_exit(pid: int, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not _pid_active(pid):
            return True
        time.sleep(0.25)
    return not _pid_active(pid)


