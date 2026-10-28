# AI-SUMMARY: 管理界面测试——flask test client + 临时 config/secrets，不碰真实配置
import pytest
import ruamel.yaml

from shared.credstore import decrypt_text
from webui.app import create_app

CONFIG_TPL = """\
project: auto_ipo

accounts:
  - id: 吴志聪
    broker: 平安证券
    account_type: normal
    enabled: true
    permissions: [cb]
    strategy: all

execution:
  mode: dry_run
"""


@pytest.fixture()
def client(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CONFIG_TPL, encoding="utf-8")
    secrets = tmp_path / "secrets.yaml"
    app = create_app(cfg, secrets)
    app.config["TESTING"] = True
    return app.test_client(), cfg, secrets


def _row(acc_id="huabao_01", broker="华宝证券", fund="99005678", pw="secret-b",
         atype="credit", orig=""):
    return {"orig_id": orig, "id": acc_id, "broker": broker, "fund_account": fund,
            "password": pw, "account_type": atype}


def _post_rows(c, rows, enabled=(), perms=None):
    data = {"orig_id": [], "id": [], "broker": [], "fund_account": [],
            "password": [], "account_type": [], "enabled": list(enabled)}
    for i, r in enumerate(rows):
        for k in ("orig_id", "id", "broker", "fund_account", "password", "account_type"):
            data[k].append(r[k])
        for p in (perms or {}).get(i, []):
            data.setdefault(f"perm_{i}", []).append(p)
    return c.post("/save", data=data, follow_redirects=True)


def test_index_layout(client):
    c, _, _ = client
    html = c.get("/").get_data(as_text=True)
    assert "平安证券" in html and "吴志聪" in html
    assert "ID（备注名）" in html
    assert "北交所打新" not in html          # 独立开关已删除
    assert "可转债" in html and "北交所" in html
    assert "沪主板" not in html              # 权限只保留 4 个准入市场
    assert "删除" in html                    # 删除路径存在
    for b in ["平安证券", "华宝证券", "中信建投", "华泰证券", "银河证券", "中信证券", "东方财富"]:
        assert b in html
    assert 'class="newrow"' in html          # 始终有空白新行


def test_save_adds_account_with_credentials(client):
    c, cfg, secrets = client
    resp = _post_rows(c, [
        _row("吴志聪", "平安证券", "88001234", "secret-a", "normal", orig="吴志聪"),
        _row(),
    ], enabled=("0", "1"), perms={0: ["cb"], 1: ["cb", "cyb"]})
    assert resp.status_code == 200
    text = cfg.read_text(encoding="utf-8")
    assert "huabao_01" in text and "credit" in text and "cyb" in text
    assert "secret-b" not in text            # 密码不进 config
    stored = ruamel.yaml.YAML().load(secrets.read_text(encoding="utf-8"))["accounts_secrets"]
    assert decrypt_text(stored["huabao_01"]["password_enc"]) == "secret-b"
    assert stored["huabao_01"]["fund_account"] == "99005678"


def test_blank_id_autofilled_from_fund_account(client):
    """修复：新行没填 ID 时不再静默丢失，自动取资金账号"""
    c, cfg, _ = client
    _post_rows(c, [
        _row("吴志聪", "平安证券", "", "", "normal", orig="吴志聪"),
        _row("", "华宝证券", "99005678", "pw"),
    ], enabled=("0", "1"))
    text = cfg.read_text(encoding="utf-8")
    assert "99005678" in text                # 自动 ID = 资金账号


def test_delete_removes_account_and_secrets(client):
    c, cfg, secrets = client
    _post_rows(c, [_row("吴志聪", "平安证券", "88001234", "pw-a", "normal", orig="吴志聪")],
               enabled=("0",))
    resp = c.post("/delete", data={"delete_id": "吴志聪"}, follow_redirects=True)
    assert resp.status_code == 200
    assert "吴志聪" not in cfg.read_text(encoding="utf-8")
    assert "88001234" not in secrets.read_text(encoding="utf-8")


def test_mode_switch(client):
    c, cfg, _ = client
    c.post("/mode", data={"mode": "live"})
    assert "mode: live" in cfg.read_text(encoding="utf-8")
    c.post("/mode", data={"mode": "dry_run"})
    assert "mode: dry_run" in cfg.read_text(encoding="utf-8")
