# AI-SUMMARY: 单同花顺客户端注册——从 execution.ths_account_switch 读取 hexin/xiadan 路径，全项目唯一客户端
from dataclasses import dataclass
from pathlib import Path

from shared.errors import AutoIpoError
from shared.paths import resolve_path


@dataclass(frozen=True)
class ClientSpec:
    client_id: str
    hexin_path: Path
    xiadan_path: Path
    enabled: bool = True

    def as_dict(self) -> dict:
        return {
            "client_id": self.client_id,
            "enabled": self.enabled,
            "hexin_path": str(self.hexin_path),
            "xiadan_path": str(self.xiadan_path),
        }


def load_client_spec(cfg: dict) -> ClientSpec:
    """唯一客户端：execution.ths_account_switch 的 hexin_path/xiadan_path。"""
    mode = (cfg.get("execution") or {}).get("ths_account_switch")
    if not isinstance(mode, dict) or not mode.get("hexin_path") or not mode.get("xiadan_path"):
        raise AutoIpoError(
            "THS_MODE_PATH_INVALID",
            "同花顺 hexin_path/xiadan_path 未配置",
            "在 config/config.yaml → execution.ths_account_switch 填写两个 exe 绝对路径",
        )
    return ClientSpec(
        client_id="ths_account_switch",
        hexin_path=resolve_path(mode["hexin_path"]),
        xiadan_path=resolve_path(mode["xiadan_path"]),
        enabled=True,
    )
