# AI-SUMMARY: 本机复制诊断——按执行模式检查依赖、配置、同花顺路径、DPAPI 与可复制性，输出结构化错误和警告
from __future__ import annotations

import importlib.util
import os
import struct
import subprocess
import sys
from datetime import datetime

from shared.paths import (
    CONFIG_FILE,
    PROJECT_ROOT,
    RUNTIME_DIR,
    SECRETS_FILE,
    ensure_runtime_dirs,
    resolve_path,
)

VENV32_PYTHON = PROJECT_ROOT / ".venv32" / "Scripts" / "python.exe"


def _check(name: str, ok: bool, detail: str = "", hint: str = "", path: str = "") -> dict:
    return {
        "name": name,
        "ok": bool(ok),
        "detail": detail,
        "hint": hint if not ok else "",
        "path": path,
        "next_action": hint if not ok else "",
    }


def _warning(code: str, message: str, hint: str = "", path: str = "") -> dict:
    return {
        "code": code,
        "message": message,
        "hint": hint,
        "path": path,
        "next_action": hint,
    }


def _module_check(name: str) -> dict:
    spec = importlib.util.find_spec(name)
    return _check(
        f"module:{name}",
        spec is not None,
        "可导入" if spec else "未安装",
        "运行 scheduler\\setup.cmd 或 python -m pip install -r requirements.txt",
    )


def _runtime32_check() -> dict:
    if not VENV32_PYTHON.is_file():
        return _check(
            "runtime32", False, f"缺少 {VENV32_PYTHON}",
            "运行 powershell -ExecutionPolicy Bypass -File scheduler\\setup.ps1",
            str(VENV32_PYTHON),
        )
    code = (
        "import struct,sys; assert struct.calcsize('P')*8==32; "
        "import pywinauto,win32gui,jqktrader,pandas,yaml,requests; print(sys.version.split()[0])"
    )
    try:
        proc = subprocess.run(
            [str(VENV32_PYTHON), "-c", code],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except Exception as exc:
        return _check(
            "runtime32", False, f"32 位环境执行失败：{type(exc).__name__}",
            "运行 scheduler\\setup.cmd 重建 .venv32", str(VENV32_PYTHON),
        )
    ok = proc.returncode == 0
    return _check(
        "runtime32", ok,
        f"Python {proc.stdout.strip()}，执行依赖可导入" if ok else (proc.stderr.strip() or "32 位依赖导入失败")[:300],
        "运行 scheduler\\setup.cmd 修复 .venv32", str(VENV32_PYTHON),
    )


def _decrypt_tokens(tokens: list[str]) -> tuple[int, int]:
    decrypted = 0
    failed = 0
    if not tokens:
        return decrypted, failed
    try:
        from shared.credstore import decrypt_text
        for token in tokens:
            decrypt_text(str(token))
            decrypted += 1
    except Exception:
        failed = len(tokens) - decrypted
    return decrypted, failed


def _account_checks(cfg: dict, secrets: dict) -> list[dict]:
    accounts = cfg.get("accounts") or []
    ids = [str(a.get("id", "")) for a in accounts]
    unique = all(ids) and len(ids) == len(set(ids))
    checks = [_check("account_ids_unique", unique, f"{len(accounts)} 个账户", "config.accounts[].id 必须唯一且非空", str(CONFIG_FILE))]
    secret_rows = secrets.get("accounts_secrets") or {}
    enabled = [str(a.get("id", "")) for a in accounts if a.get("enabled")]
    missing = [item for item in enabled if not isinstance(secret_rows.get(item), dict) or not secret_rows[item].get("fund_account")]
    checks.append(_check(
        "enabled_account_secrets", not missing,
        f"{len(enabled) - len(missing)}/{len(enabled)} 个启用账户有资金账号元数据",
        "为启用账户补 fund_account；换机必须重新录入",
        str(SECRETS_FILE),
    ))
    from execution.account_session import hash_fund_account
    seen = {}
    duplicates = []
    for account_id, row in secret_rows.items():
        fund_account = row.get("fund_account") if isinstance(row, dict) else ""
        if not fund_account:
            continue
        value = hash_fund_account(str(fund_account))
        if value in seen:
            duplicates.append(f"{seen[value]}={account_id}")
        seen[value] = account_id
    checks.append(_check(
        "unique_fund_accounts", not duplicates,
        "资金账号唯一" if not duplicates else "重复：" + "、".join(duplicates),
        "同一资金账号只能配置一次，禁止跨客户端重复执行",
        str(SECRETS_FILE),
    ))
    return checks


def _ths_account_checks(cfg: dict) -> tuple[list[dict], list[dict]]:
    mode = (cfg.get("execution") or {}).get("ths_account_switch") or {}
    raw_accounts = mode.get("accounts") if isinstance(mode.get("accounts"), list) else []
    names = [str(row.get("username") or "").strip() if isinstance(row, dict) else "" for row in raw_accounts]
    nonempty = [name for name in names if name]
    unique = len(nonempty) == len(set(nonempty)) and len(nonempty) == len(names)
    count_ok = 1 <= len(names) <= 10 and unique

    checks = [
        _check(
            "ths_display_names_unique", unique,
            f"{len(nonempty)} 个有效显示名",
            "execution.ths_account_switch.accounts[].username 必须非空且唯一",
            str(CONFIG_FILE),
        ),
        _check(
            "ths_account_count", count_ok,
            f"{len(names)} 个同花顺登录账户",
            "同花顺登录账户总数必须为 1 到 10，且显示名不得为空或重复",
            str(CONFIG_FILE),
        ),
    ]
    warnings: list[dict] = []
    for kind, key in (("hexin", "hexin_path"), ("xiadan", "xiadan_path")):
        raw_path = str(mode.get(key) or "").strip()
        path = resolve_path(raw_path) if raw_path else PROJECT_ROOT / f"<missing-{kind}>"
        checks.append(_check(
            f"ths_client:{kind}", bool(raw_path) and path.is_file(), str(path),
            f"修改 execution.ths_account_switch.{key} 指向真实 exe", str(path),
        ))
    return checks, warnings


def _ths_dpapi_check(names: list[str], secrets: dict) -> tuple[dict, list[dict]]:
    rows = secrets.get("ths_account_secrets") or {}
    missing: list[str] = []
    tokens: list[str] = []
    for name in names:
        row = rows.get(name) or {}
        token = row.get("password_enc") if isinstance(row, dict) else ""
        if token:
            tokens.append(str(token))
        else:
            missing.append(name)
    decrypted, failed = _decrypt_tokens(tokens)
    detail = f"配置 {decrypted + failed}/{len(names)}，缺失 {len(missing)}"
    check = _check("ths_dpapi_passwords", True, detail, "", str(SECRETS_FILE))
    warnings: list[dict] = []
    if missing:
        warnings.append(_warning(
            "THS_PASSWORD_OPTIONAL_MISSING",
            f"{len(missing)} 个同花顺账户未配置 DPAPI 密码密文；客户端已保存密码时仍可尝试登录",
            "需要自动填写密码时，在 config/secrets.yaml 的 ths_account_secrets.<username>.password_enc 写入本机 DPAPI 密文",
            str(SECRETS_FILE),
        ))
    if failed:
        warnings.append(_warning(
            "THS_PASSWORD_DECRYPT_FAILED",
            f"{failed} 个同花顺账户的 DPAPI 密码密文无法由当前 Windows 用户解密",
            "换电脑或换 Windows 用户后重新录入密码；不得复制明文或旧密文",
            str(SECRETS_FILE),
        ))
    return check, warnings


def _base_checks() -> list[dict]:
    return [
        _check("project_root", PROJECT_ROOT.is_dir(), str(PROJECT_ROOT), "项目目录不可用", str(PROJECT_ROOT)),
        _check("runtime_writable", os.access(RUNTIME_DIR, os.W_OK), str(RUNTIME_DIR),
               "给当前用户 runtime_data 完全控制权限", str(RUNTIME_DIR)),
        _check("python_version", sys.version_info >= (3, 12), sys.version.split()[0], "安装 64 位 Python 3.12", sys.executable),
        _check("python_bitness", struct.calcsize("P") * 8 == 64, f"{struct.calcsize('P') * 8} 位",
               "通用命令必须使用 64 位 Python 3.12", sys.executable),
        _check("requirements_files", (PROJECT_ROOT / "requirements.txt").is_file() and (PROJECT_ROOT / "execution" / "requirements32.txt").is_file(),
               "64/32 位依赖清单", "恢复 requirements.txt 与 execution/requirements32.txt", str(PROJECT_ROOT)),
        _check("config_exists", CONFIG_FILE.is_file(), str(CONFIG_FILE), "复制 config/config.example.yaml 为 config.yaml", str(CONFIG_FILE)),
        _check("secrets_file", SECRETS_FILE.is_file(), str(SECRETS_FILE), "复制 config/secrets.example.yaml 为 secrets.yaml", str(SECRETS_FILE)),
        _module_check("yaml"),
        _module_check("requests"),
        _module_check("pytest"),
        _module_check("win32api"),
        _runtime32_check(),
    ]


def run_doctor(cfg: dict | None = None, secrets: dict | None = None) -> dict:
    ensure_runtime_dirs()
    checks = _base_checks()
    warnings: list[dict] = []
    try:
        if cfg is None or secrets is None:
            from shared.config import load_config, load_secrets
            cfg = load_config() if cfg is None else cfg
            secrets = load_secrets() if secrets is None else secrets
        checks.append(_check("config_parse", True))
        ths_checks, mode_warnings = _ths_account_checks(cfg)
        checks.extend(ths_checks)
        warnings.extend(mode_warnings)
        names = [
            str(row.get("username") or "").strip()
            for row in ((cfg.get("execution") or {}).get("ths_account_switch") or {}).get("accounts") or []
            if isinstance(row, dict) and str(row.get("username") or "").strip()
        ]
        dpapi_check, dpapi_warnings = _ths_dpapi_check(names, secrets)
        checks.append(dpapi_check)
        warnings.extend(dpapi_warnings)
        checks.extend(_account_checks(cfg, secrets))
    except Exception as exc:
        checks.append(_check("config_parse", False, str(exc), "按错误信息修复配置", str(CONFIG_FILE)))
    errors = [{
        "code": item["name"].upper().replace(":", "_"),
        "message": item["detail"],
        "hint": item["hint"],
        "path": item["path"],
        "next_action": item["next_action"],
    } for item in checks if not item["ok"]]
    return {
        "ok": not errors,
        "project_root": str(PROJECT_ROOT),
        "python": {"version": sys.version.split()[0], "bits": struct.calcsize("P") * 8, "executable": sys.executable},
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }



