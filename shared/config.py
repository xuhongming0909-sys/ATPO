# AI-SUMMARY: 统一加载 config/config.yaml 与 config/secrets.yaml——路径由 shared.paths 解析，错误带修复提示
import yaml

from shared.errors import AutoIpoError
from shared.paths import CONFIG_FILE, SECRETS_FILE


def _load_yaml(path, code: str, required: bool) -> dict:
    if not path.exists():
        if not required:
            return {}
        raise AutoIpoError(
            code,
            f"配置文件不存在：{path}",
            "复制对应 example 文件并填写，然后运行 python run.py doctor",
            {"path": str(path)},
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AutoIpoError(
            "CONFIG_YAML_INVALID",
            f"YAML 解析失败：{path}",
            "检查缩进、冒号和引号；禁止在 YAML 中使用 Tab",
            {"path": str(path), "detail": str(exc)[:120]},
        ) from exc
    return data or {}


def load_config() -> dict:
    cfg = _load_yaml(CONFIG_FILE, "CONFIG_MISSING", required=True)
    if not isinstance(cfg, dict):
        raise AutoIpoError(
            "CONFIG_STRUCTURE_INVALID",
            "config.yaml 顶层必须是映射",
            "从 config/config.example.yaml 重新复制结构",
            {"path": str(CONFIG_FILE)},
        )
    return cfg


def load_secrets() -> dict:
    data = _load_yaml(SECRETS_FILE, "SECRETS_MISSING", required=False)
    if not isinstance(data, dict):
        raise AutoIpoError(
            "SECRETS_STRUCTURE_INVALID",
            "secrets.yaml 顶层必须是映射",
            "从 config/secrets.example.yaml 重新复制结构",
            {"path": str(SECRETS_FILE)},
        )
    return data
