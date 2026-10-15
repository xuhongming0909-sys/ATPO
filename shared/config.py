# AI-SUMMARY: 统一加载 config/config.yaml（非敏感）与 config/secrets.yaml（敏感），提供配置访问入口
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


def load_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "config.yaml").read_text(encoding="utf-8"))


def load_secrets() -> dict:
    path = CONFIG_DIR / "secrets.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
