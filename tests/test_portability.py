# AI-SUMMARY: 可复制性基础测试——统一路径、错误提示和 doctor 输出结构不泄露敏感值
import json
from pathlib import Path

from shared.doctor import run_doctor
from shared.errors import AutoIpoError, format_error
from shared.paths import PROJECT_ROOT, resolve_path


def test_relative_paths_resolve_from_project_root():
    assert resolve_path("runtime_data/x.png") == PROJECT_ROOT / "runtime_data" / "x.png"


def test_error_format_has_code_and_hint():
    err = AutoIpoError("CLIENT_WINDOW_MISSING", "找不到窗口", "关闭残留进程", {"client_id": "ths2"})
    text = format_error(err)
    assert "[CLIENT_WINDOW_MISSING]" in text
    assert "关闭残留进程" in text
    assert "client_id=ths2" in text


def test_doctor_returns_complete_machine_readable_report():
    result = run_doctor()
    assert set(result) >= {"ok", "project_root", "python", "checks", "errors"}
    assert result["project_root"] == str(PROJECT_ROOT)
    assert all({"name", "ok", "detail", "hint", "path", "next_action"} <= set(item) for item in result["checks"])
    names = {item["name"] for item in result["checks"]}
    assert {"runtime32", "enabled_account_secrets", "unique_fund_accounts"} <= names
    assert all({"code", "message", "hint", "path", "next_action"} <= set(item) for item in result["errors"])
    json.dumps(result, ensure_ascii=False)
