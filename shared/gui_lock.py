# AI-SUMMARY: 全局 GUI 原子锁——跨计划任务/进程阻止同花顺自动操作互相抢焦点
import contextlib
import ctypes
import os
import time
from datetime import datetime
from uuid import uuid4

from shared.errors import AutoIpoError
from shared.paths import ensure_runtime_dirs, runtime_path

STALE_LOCK_S = 2 * 60 * 60


def _pid_active(pid: int) -> bool:
    if pid <= 0:
        return False
    process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not process:
        return False
    try:
        code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(process, ctypes.byref(code)):
            return False
        return code.value == 259
    finally:
        ctypes.windll.kernel32.CloseHandle(process)


def _stale_owner(path) -> bool:
    try:
        parts = path.read_text(encoding="utf-8").split("|", 3)
        owner_pid = int(parts[0])
        created_at = datetime.fromisoformat(parts[2])
        return not _pid_active(owner_pid) or (datetime.now() - created_at).total_seconds() > STALE_LOCK_S
    except Exception:
        return True


@contextlib.contextmanager
def gui_lock(operation: str, timeout_s: float = 10.0):
    ensure_runtime_dirs()
    path = runtime_path("gui.lock")
    marker = f"{os.getpid()}|{operation}|{datetime.now().isoformat(timespec='seconds')}|{uuid4().hex}"
    deadline = time.time() + timeout_s
    fd = None
    while fd is None:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _stale_owner(path):
                try:
                    path.unlink()
                except OSError:
                    pass
            if time.time() >= deadline:
                owner = ""
                try:
                    owner = path.read_text(encoding="utf-8")[:200]
                except Exception:
                    pass
                raise AutoIpoError(
                    "GUI_LOCK_BUSY",
                    "另一个自动化任务正在操作 GUI",
                    "等待当前任务结束；不要同时手动操作同花顺",
                    {"operation": operation, "owner": owner},
                )
            time.sleep(0.25)
    try:
        os.write(fd, marker.encode("utf-8"))
        os.close(fd)
        fd = None
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            current = path.read_text(encoding="utf-8")
            if current == marker:
                path.unlink()
        except OSError:
            pass