# AI-SUMMARY: 新模式诊断与干净打包测试——全用临时目录/桩对象，不触券商客户端、不发送推送
from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import shared.doctor as doctor


def _base_tree(tmp_path: Path) -> None:
    (tmp_path / "runtime_data").mkdir()
    (tmp_path / "execution").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    (tmp_path / "execution" / "requirements32.txt").write_text("pywinauto\n", encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text("execution: {}\n", encoding="utf-8")
    (tmp_path / "config" / "secrets.yaml").write_text("{}\n", encoding="utf-8")


def _mock_doctor_env(monkeypatch, tmp_path: Path) -> None:
    _base_tree(tmp_path)
    monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(doctor, "RUNTIME_DIR", tmp_path / "runtime_data")
    monkeypatch.setattr(doctor, "CONFIG_FILE", tmp_path / "config" / "config.yaml")
    monkeypatch.setattr(doctor, "SECRETS_FILE", tmp_path / "config" / "secrets.yaml")
    monkeypatch.setattr(doctor, "VENV32_PYTHON", tmp_path / ".venv32" / "Scripts" / "python.exe")
    monkeypatch.setattr(doctor, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(doctor, "_module_check", lambda name: doctor._check(f"module:{name}", True, "mock"))
    monkeypatch.setattr(doctor, "_runtime32_check", lambda: doctor._check("runtime32", True, "mock .venv32"))


def _ths_cfg(tmp_path: Path, names: list[str]) -> dict:
    hexin = tmp_path / "hexin.exe"
    xiadan = tmp_path / "xiadan.exe"
    hexin.write_bytes(b"mock")
    xiadan.write_bytes(b"mock")
    return {
        "execution": {
            "active_mode": "ths_account_switch",
            "ths_account_switch": {
                "hexin_path": str(hexin),
                "xiadan_path": str(xiadan),
                "accounts": [{"username": name, "enabled": True} for name in names],
            },
        }
    }


def test_ths_mode_does_not_require_legacy_fund_accounts(monkeypatch, tmp_path):
    _mock_doctor_env(monkeypatch, tmp_path)
    cfg = _ths_cfg(tmp_path, ["mx_one", "mx_two"])

    result = doctor.run_doctor(cfg=cfg, secrets={})

    assert result["ok"] is True
    names = {item["name"]: item for item in result["checks"]}
    assert names["ths_display_names_unique"]["ok"] is True
    assert names["ths_account_count"]["ok"] is True
    assert names["ths_client:hexin"]["ok"] is True
    assert names["ths_client:xiadan"]["ok"] is True
    assert names["runtime32"]["ok"] is True
    assert names["enabled_account_secrets"]["ok"] is True
    assert names["unique_fund_accounts"]["ok"] is True
    warning_codes = {item["code"] for item in result["warnings"]}
    assert "THS_PASSWORD_OPTIONAL_MISSING" in warning_codes
    text = json.dumps(result, ensure_ascii=False)
    assert "WebUI" not in text
    assert '"fund_account":' not in text
    json.dumps(result, ensure_ascii=False)


def test_ths_mode_rejects_duplicate_or_out_of_range_accounts(monkeypatch, tmp_path):
    _mock_doctor_env(monkeypatch, tmp_path)

    duplicate = doctor.run_doctor(cfg=_ths_cfg(tmp_path, ["mx_one", "mx_one"]), secrets={})
    too_many = doctor.run_doctor(cfg=_ths_cfg(tmp_path, [f"mx_{i}" for i in range(11)]), secrets={})
    empty = doctor.run_doctor(cfg=_ths_cfg(tmp_path, []), secrets={})

    for result in (duplicate, too_many, empty):
        assert result["ok"] is False
    duplicate_names = {item["code"] for item in duplicate["errors"]}
    many_names = {item["code"] for item in too_many["errors"]}
    empty_names = {item["code"] for item in empty["errors"]}
    assert "THS_DISPLAY_NAMES_UNIQUE" in duplicate_names
    assert "THS_ACCOUNT_COUNT" in many_names
    assert "THS_ACCOUNT_COUNT" in empty_names


def test_ths_dpapi_passwords_are_optional_and_warn_on_decrypt_failure(monkeypatch, tmp_path):
    _mock_doctor_env(monkeypatch, tmp_path)
    cfg = _ths_cfg(tmp_path, ["mx_one"])
    secrets = {"ths_account_secrets": {"mx_one": {"password_enc": "cipher"}}}
    monkeypatch.setattr("shared.credstore.decrypt_text", lambda _token: "mock-password")

    valid = doctor.run_doctor(cfg=cfg, secrets=secrets)
    assert valid["ok"] is True
    assert {item["code"] for item in valid["warnings"]} == set()

    def _fail(_token):
        raise RuntimeError("plaintext must not leak")

    monkeypatch.setattr("shared.credstore.decrypt_text", _fail)
    broken = doctor.run_doctor(cfg=cfg, secrets=secrets)
    assert broken["ok"] is True
    assert {item["code"] for item in broken["warnings"]} == {"THS_PASSWORD_DECRYPT_FAILED"}
    assert "plaintext must not leak" not in json.dumps(broken, ensure_ascii=False)


def test_single_mode_account_checks(monkeypatch, tmp_path):
    _mock_doctor_env(monkeypatch, tmp_path)
    hexin = tmp_path / "hexin.exe"
    xiadan = tmp_path / "xiadan.exe"
    hexin.write_bytes(b"mock")
    xiadan.write_bytes(b"mock")
    cfg = {
        "accounts": [{"id": "甲", "enabled": True}],
        "execution": {
            "ths_account_switch": {
                "hexin_path": str(hexin), "xiadan_path": str(xiadan),
                "max_ths_accounts": 10, "max_fund_accounts_per_ths": 10,
                "accounts": [{"username": "mx_1", "enabled": True}],
            },
        },
    }
    secrets = {"accounts_secrets": {"甲": {"fund_account": "1234", "password_enc": ""}}}

    result = doctor.run_doctor(cfg=cfg, secrets=secrets)

    assert result["ok"] is True
    names = {item["name"] for item in result["checks"]}
    assert {"enabled_account_secrets", "unique_fund_accounts", "ths_client:hexin", "ths_client:xiadan"} <= names


def _fixture_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "scheduler").mkdir()
    (root / "runtime_data" / "screenshots").mkdir(parents=True)
    (root / ".venv32" / "Scripts").mkdir(parents=True)
    (root / "__pycache__").mkdir()
    (root / ".pytest_cache").mkdir()
    (root / ".git").mkdir()
    (root / "nested").mkdir()

    (root / "config" / "config.yaml").write_text("execution: {}\n", encoding="utf-8")
    (root / "config" / "secrets.example.yaml").write_text("serverchan: {}\n", encoding="utf-8")
    (root / "config" / "secrets.yaml").write_text("secret: cipher\n", encoding="utf-8")
    (root / "docs" / "spec.md").write_text("# spec\n", encoding="utf-8")
    (root / "docs" / "screenshot-account.png").write_bytes(b"png")
    (root / "docs" / "diagram.png").write_bytes(b"png")
    (root / "scheduler" / "register_tasks.ps1").write_text("# tasks\n", encoding="utf-8")
    (root / "runtime_data" / "screenshots" / "account.png").write_bytes(b"png")
    (root / ".venv32" / "Scripts" / "python.exe").write_bytes(b"exe")
    (root / "__pycache__" / "x.pyc").write_bytes(b"cache")
    (root / ".pytest_cache" / "v").write_text("cache\n", encoding="utf-8")
    (root / ".git" / "config").write_text("git\n", encoding="utf-8")
    (root / "nested" / "secrets.yaml").write_text("secret: cipher\n", encoding="utf-8")
    return root


def _run_package(script: Path, root: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ProjectRoot",
            str(root),
            "-OutputPath",
            str(output),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def test_package_project_excludes_sensitive_and_cache_content(tmp_path):
    root = _fixture_project(tmp_path)
    output = root / "runtime_data" / "package" / "auto-ipo-clean.zip"
    script = Path(doctor.__file__).resolve().parent.parent / "scheduler" / "package_project.ps1"

    first = _run_package(script, root, output)
    second = _run_package(script, root, output)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert output.is_file()
    with zipfile.ZipFile(output) as archive:
        names = {name.replace("\\", "/").rstrip("/") for name in archive.namelist()}
        assert {"config/config.yaml", "config/secrets.example.yaml", "docs/spec.md", "scheduler/register_tasks.ps1"} <= names
        assert "docs/diagram.png" in names
        for forbidden in (
            "config/secrets.yaml",
            "nested/secrets.yaml",
            "runtime_data",
            ".venv32",
            "__pycache__",
            ".pytest_cache",
            ".git",
            "docs/screenshot-account.png",
        ):
            assert all(forbidden not in name for name in names), forbidden
    assert not list((root / "runtime_data" / "package").glob(".package-*"))


def test_package_project_rejects_output_outside_workspace(tmp_path):
    root = _fixture_project(tmp_path)
    output = tmp_path.parent / "outside-auto-ipo.zip"
    script = Path(doctor.__file__).resolve().parent.parent / "scheduler" / "package_project.ps1"

    result = _run_package(script, root, output)

    assert result.returncode != 0
    assert "PACKAGE_PATH_OUTSIDE_WORKSPACE" in result.stderr
    assert not output.exists()
