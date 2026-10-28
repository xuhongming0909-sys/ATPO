# AI-SUMMARY: 客户端进程与窗口隔离——只接受指定 exe 路径所属 PID/窗口，防止双实例串线

import subprocess

from pathlib import Path

from typing import Callable



from execution.client_registry import ClientSpec

from shared.errors import AutoIpoError





def pids_for_image(image: str, _runner: Callable = subprocess.run) -> set[int]:
    out = _runner(
        ["tasklist", "/fi", f"imagename eq {image}", "/fo", "csv", "/nh"],
        capture_output=True, text=True, errors="ignore",
    ).stdout or ""
    pids = set()
    for line in out.splitlines():
        parts = line.split('","')
        if len(parts) > 1 and parts[0].strip('"').lower() == image.lower():
            pids.add(int(parts[1].strip('"')))
    if pids:
        return pids
    proc = _runner(
        ["powershell.exe", "-NoProfile", "-Command",
         f"Get-Process -Name '{Path(image).stem}' -ErrorAction SilentlyContinue | Select-Object Id | ConvertTo-Json -Compress"],
        capture_output=True, text=True, errors="ignore",
    )
    try:
        import json

        rows = json.loads(proc.stdout or "[]")
        if isinstance(rows, dict):
            rows = [rows]
        return {int(row["Id"]) for row in rows if str(row.get("Id", "")).isdigit()}
    except Exception:
        return set()

def executable_path_for_pid(pid: int) -> Path | None:

    import win32api

    import win32con

    import win32process



    handle = None

    try:

        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION, False, int(pid))

        return Path(win32process.GetModuleFileNameEx(handle, 0))

    except Exception:

        return None

    finally:

        if handle is not None:

            try:

                win32api.CloseHandle(handle)

            except Exception:

                pass





def _executable_path_wmi(pid: int) -> Path | None:
    """WMI 查询进程映像路径（OpenProcess 失败时的兜底）。"""
    import subprocess

    try:
        proc = subprocess.run(
            ["wmic", "process", "where", f"ProcessId={int(pid)}", "get", "ExecutablePath", "/format:list"],
            capture_output=True, text=True, errors="ignore", timeout=10, check=False,
        )
    except Exception:
        return None
    for line in (proc.stdout or "").splitlines():
        if line.startswith("ExecutablePath="):
            value = line.split("=", 1)[1].strip()
            return Path(value) if value else None
    return None


def pids_for_executable(exe_path: Path, *, _pids: Callable = pids_for_image,

                        _exe_for_pid: Callable = executable_path_for_pid) -> set[int]:

    wanted = Path(exe_path).resolve()

    result = set()

    for pid in _pids(wanted.name):

        current = _exe_for_pid(pid)

        if current is not None and Path(current).resolve() == wanted:

            result.add(int(pid))

    return result





def client_pids(spec: ClientSpec) -> tuple[set[int], set[int]]:

    return (

        pids_for_executable(spec.hexin_path),

        pids_for_executable(spec.xiadan_path),

    )





def windows_for_pids(pids: set[int], *, class_prefix: str = "", title_has: str = "",

                     visible_only: bool = True, _desktop=None):

    from pywinauto import Desktop



    desktop = _desktop or Desktop(backend="win32")

    found = []

    for window in desktop.windows():

        try:

            if int(window.process_id()) not in pids:

                continue

            if visible_only and not window.is_visible():

                continue

            if class_prefix and not str(window.class_name()).startswith(class_prefix):

                continue

            if title_has and title_has not in str(window.window_text()):

                continue

            found.append(window)

        except Exception:

            continue

    return found





def require_single_window(windows: list, client_id: str, kind: str):

    if len(windows) != 1:

        raise AutoIpoError(

            "CLIENT_WINDOW_AMBIGUOUS" if windows else "CLIENT_WINDOW_MISSING",

            f"客户端 {client_id} 的 {kind} 窗口数量为 {len(windows)}",

            "关闭重复客户端/残留进程后运行 python run.py doctor",

            {"client_id": client_id, "window_kind": kind, "count": len(windows)},

        )

    return windows[0]

