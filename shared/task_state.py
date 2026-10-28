# AI-SUMMARY: 本地幂等任务状态——按任务/业务日期/执行模式记录完成、回执和脱敏错误
from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.errors import AutoIpoError
from shared.paths import ensure_runtime_dirs, runtime_path

SENSITIVE_KEYS = {
    "password", "password_enc", "交易密码", "captcha", "验证码", "sendkey", "token",
}
@dataclass
class TaskState:
    task: str
    date: str
    status: str
    completed_at: str = ""
    receipt_status: str = "not_sent"
    sanitized_error: str = ""
    mode: str = ""
    payload: Any | None = None

    @property
    def key(self) -> str:
        return "|".join((self.task, self.date, self.mode))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def sanitize(value: Any) -> Any:
    """递归移除凭据字段；账户识别信息完整保留（本机自用）。"""
    if isinstance(value, dict):
        return {
            str(k): ("***" if str(k).lower() in SENSITIVE_KEYS else sanitize(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        return re.sub(
            r"(password|passwd|pwd|密码|captcha|验证码|sendkey|secret|token)(\s*[:=：]\s*)[^\s｜|，,;；]+",
            r"\1\2***", value, flags=re.I,
        )
    return value


def sanitize_error(exc: Exception | str) -> str:
    return sanitize(str(exc))[:500]


def result_signature(value: Any) -> str:
    """结构化结果指纹：脱敏后按稳定键序哈希，用于查询结果未变化不重复推送。"""
    canonical = json.dumps(sanitize(value), ensure_ascii=False, sort_keys=True, default=str)
    raw = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


@contextmanager
def _state_lock(path: Path):
    ensure_runtime_dirs()
    lock = path.with_name(path.name + ".lock")
    deadline = datetime.now().timestamp() + 5
    fd = None
    while fd is None:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                created = lock.stat().st_mtime
                if datetime.now().timestamp() - created > 30:
                    lock.unlink()
                    continue
            except OSError:
                pass
            if datetime.now().timestamp() >= deadline:
                raise AutoIpoError(
                    "TASK_STATE_BUSY",
                    "任务状态文件正在被其他进程更新",
                    "等待几秒后重试；不要并行启动同一自动化任务",
                    {"path": str(lock)},
                )
    try:
        os.close(fd)
        yield
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


class TaskStateStore:
    """JSON 任务状态库；成功且已推送的记录阻止重复执行。"""

    def __init__(self, path: Path | None = None):
        self.path = path or runtime_path("task_state.json")

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("tasks"), dict):
                return data
        except FileNotFoundError:
            pass
        except Exception as exc:
            raise AutoIpoError(
                "TASK_STATE_CORRUPT",
                "任务状态文件损坏",
                "备份并删除 runtime_data/task_state.json 后重试",
                {"path": str(self.path), "error": sanitize_error(exc)},
            ) from exc
        return {"version": 1, "tasks": {}}

    def get(self, task: str, day: str, mode: str = "") -> TaskState | None:
        raw = self._read()["tasks"].get("|".join((task, day, mode)))
        return TaskState(**raw) if isinstance(raw, dict) else None

    def list(self) -> list[TaskState]:
        return [TaskState(**raw) for raw in self._read()["tasks"].values() if isinstance(raw, dict)]

    def record(
        self,
        task: str,
        day: str,
        status: str,
        *,
        receipt_status: str = "not_sent",
        error: Exception | str = "",
        mode: str = "",
        payload: Any = None,
        completed_at: str | None = None,
    ) -> TaskState:
        ensure_runtime_dirs()
        item = TaskState(
            task=str(task),
            date=str(day),
            status=str(status),
            completed_at=completed_at or datetime.now().isoformat(timespec="seconds"),
            receipt_status=str(receipt_status or "not_sent"),
            sanitized_error=sanitize_error(error) if error else "",
            mode=str(mode),
            payload=sanitize(payload) if payload is not None else None,
        )
        with _state_lock(self.path):
            data = self._read()
            data["tasks"][item.key] = item.as_dict()
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
            tmp.replace(self.path)
        return item

    def should_skip(self, task: str, day: str, mode: str = "", receipt_required: bool = True) -> TaskState | None:
        item = self.get(task, day, mode)
        if item is None:
            return None
        if item.status in {"skipped_expired", "skipped_completed", "blocked_uncertain"}:
            return item
        if item.status == "completed" and (not receipt_required or item.receipt_status in {"sent", "skipped", "not_required"}):
            return item
        return None
