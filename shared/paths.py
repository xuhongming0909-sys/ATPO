# AI-SUMMARY: 项目统一路径入口——配置、运行时目录和相对路径均从项目根目录解析
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
SECRETS_FILE = CONFIG_DIR / "secrets.yaml"
RUNTIME_DIR = PROJECT_ROOT / "runtime_data"

RUNTIME_SUBDIRS = (
    "logs",
    "screenshots",
    "results",
    "order_ledger",
    "errors",
    "diagnostics",
    "boot_login",
)


def resolve_path(value: str | Path) -> Path:
    raw = os.path.expandvars(os.path.expanduser(str(value)))
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def runtime_path(*parts: str) -> Path:
    return RUNTIME_DIR.joinpath(*parts)


def ensure_runtime_dirs() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_SUBDIRS:
        (RUNTIME_DIR / name).mkdir(parents=True, exist_ok=True)
