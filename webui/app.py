# AI-SUMMARY: 本地管理界面（Web 表单）——账户增删改/凭据录入/模式切换；ID 即备注（可中文）；密码 DPAPI 加密存 secrets.yaml；只监听本机
from pathlib import Path

from flask import Flask, redirect, render_template_string, request
from ruamel.yaml import YAML

from shared.credstore import encrypt_text
from shared.paths import CONFIG_FILE, SECRETS_FILE

DEFAULT_CONFIG = CONFIG_FILE
DEFAULT_SECRETS = SECRETS_FILE

# 只保留权限准入市场；沪深主板无需权限（市值由柜台裁决）
PERMISSIONS = [("cb", "可转债"), ("cyb", "创业板"), ("kcb", "科创板"), ("bj", "北交所")]
BROKERS = ["平安证券", "华宝证券", "中信建投", "华泰证券", "银河证券", "中信证券", "东方财富"]

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>自动打新 · 账户管理</title>
<style>
body{font-family:"Microsoft YaHei",sans-serif;max-width:1280px;margin:24px auto;padding:0 16px;color:#222}
h1{font-size:20px} h2{font-size:16px;margin-top:28px}
table{border-collapse:collapse;width:100%} td,th{border:1px solid #ddd;padding:6px 8px;font-size:14px;text-align:left}
input[type=text],input[type=password]{width:110px;padding:4px} select{padding:4px}
button{padding:6px 14px;font-size:14px;cursor:pointer}
.del{color:#c00;background:none;border:none;text-decoration:underline;padding:2px}
.mode{display:inline-block;padding:4px 12px;border-radius:4px;font-weight:bold}
.mode.live{background:#ffe4e4;color:#c00}.mode.dry_run{background:#e4f0e4;color:#060}
.hint{color:#888;font-size:13px}
tr.newrow{background:#f7f9fc}
</style></head><body>
<h1>自动打新 · 账户管理</h1>
<h2>执行模式：<span class="mode {{ mode }}">{{ mode }}</span></h2>
<form method="post" action="/mode">
  <button name="mode" value="live">切换到实盘 live</button>
  <button name="mode" value="dry_run">切换到演练 dry_run</button>
  <span class="hint">实盘仅在工作日 10:00 定时任务触发（另需命令行带 --live，双保险）</span>
</form>

<h2>账户列表</h2>
<form method="post" action="/save">
<table><tr><th>ID（备注名）</th><th>券商</th><th>资金账号</th><th>交易密码</th><th>账户类型</th><th>自动打新</th><th>已开通权限</th><th>操作</th></tr>
{% for a in accounts %}
<tr>
  <td><input type="hidden" name="orig_id" value="{{ a.id }}">
      <input type="text" name="id" value="{{ a.id }}"></td>
  <td><input type="text" name="broker" value="{{ a.broker }}" list="brokers"></td>
  <td><input type="text" name="fund_account" value="{{ a.fund_account }}"></td>
  <td><input type="password" name="password" placeholder="{{ '已保存，不改请留空' if a.has_password else '未设置' }}"></td>
  <td><select name="account_type">
    <option value="normal" {{ "selected" if a.account_type=="normal" }}>普通</option>
    <option value="credit" {{ "selected" if a.account_type=="credit" }}>信用</option>
  </select></td>
  <td><input type="checkbox" name="enabled" value="{{ loop.index0 }}" {{ "checked" if a.enabled }}></td>
  <td>{% set outer_i = loop.index0 %}{% for key, label in permissions %}
    <label><input type="checkbox" name="perm_{{ outer_i }}" value="{{ key }}" {{ "checked" if key in a.permissions }}>{{ label }}</label>
  {% endfor %}<div class="hint">勾选的市场才打新</div></td>
  <td><button class="del" type="submit" name="delete_id" value="{{ a.id }}" formaction="/delete">删除</button></td>
</tr>
{% endfor %}
<tr class="newrow">
  <td><input type="hidden" name="orig_id" value=""><input type="text" name="id" placeholder="新账户 ID（可中文）" style="width:130px"></td>
  <td><input type="text" name="broker" list="brokers" placeholder="券商"></td>
  <td><input type="text" name="fund_account" placeholder="资金账号"></td>
  <td><input type="password" name="password" placeholder="交易密码"></td>
  <td><select name="account_type"><option value="normal">普通</option><option value="credit">信用</option></select></td>
  <td><input type="checkbox" name="enabled" value="{{ accounts|length }}" checked></td>
  <td>{% for key, label in permissions %}<label><input type="checkbox" name="perm_{{ accounts|length }}" value="{{ key }}">{{ label }}</label>{% endfor %}</td>
  <td></td>
</tr>
</table>
<datalist id="brokers">{% for b in brokers %}<option value="{{ b }}">{% endfor %}</datalist>
<p><button type="submit">保存全部</button> <span class="hint">最后一行永远留空待填；填完保存后会自动出现新的空行。ID 留空时自动取资金账号。</span></p>
</form>
<p class="hint">交易密码用 Windows DPAPI 加密后存本机 config/secrets.yaml（绑定当前 Windows 用户，其他电脑/用户解不开），不进 git、不进日志、不进推送。</p>
</body></html>"""


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    return y


def create_app(config_path: Path | None = None, secrets_path: Path | None = None) -> Flask:
    cfg_path = Path(config_path or DEFAULT_CONFIG)
    sec_path = Path(secrets_path or DEFAULT_SECRETS)
    app = Flask(__name__)

    def load_yaml(p: Path) -> dict:
        if not p.exists():
            return {}
        return _yaml().load(p.read_text(encoding="utf-8")) or {}

    def save_yaml(p: Path, data: dict) -> None:
        with open(p, "w", encoding="utf-8") as f:
            _yaml().dump(data, f)

    @app.get("/")
    def index():
        cfg = load_yaml(cfg_path)
        secrets = (load_yaml(sec_path).get("accounts_secrets") or {})
        accounts = cfg.get("accounts") or []
        for a in accounts:  # 模板需要的默认值补齐
            a.setdefault("account_type", "normal")
            a.setdefault("permissions", [])
            a.setdefault("enabled", True)
            sec = secrets.get(a["id"]) or {}
            a["fund_account"] = sec.get("fund_account", "")
            a["has_password"] = bool(sec.get("password_enc"))
        return render_template_string(
            PAGE, accounts=accounts, permissions=PERMISSIONS, brokers=BROKERS,
            mode=(cfg.get("execution") or {}).get("mode", "dry_run"),
        )

    @app.post("/save")
    def save_accounts():
        cfg = load_yaml(cfg_path)
        secrets = load_yaml(sec_path)
        acc_secrets = secrets.setdefault("accounts_secrets", {})

        orig_ids = request.form.getlist("orig_id")
        ids = request.form.getlist("id")
        brokers = request.form.getlist("broker")
        fund_accounts = request.form.getlist("fund_account")
        passwords = request.form.getlist("password")
        types = request.form.getlist("account_type")
        enabled_idx = set(map(int, request.form.getlist("enabled")))

        accounts = []
        for i, acc_id in enumerate(ids):
            acc_id = acc_id.strip()
            broker = brokers[i].strip()
            fund_account = fund_accounts[i].strip()
            if not acc_id:
                # ID 留空：行内无有效数据则忽略；有数据则以资金账号为 ID（不再静默丢行）
                if not (broker or fund_account or passwords[i]):
                    continue
                acc_id = fund_account or f"{broker}_{i}"
            accounts.append({
                "id": acc_id,
                "broker": broker,
                "account_type": types[i],
                "enabled": i in enabled_idx,
                "permissions": request.form.getlist(f"perm_{i}"),
                "strategy": "all",
            })
            orig = orig_ids[i].strip()
            if orig and orig != acc_id and orig in acc_secrets:
                acc_secrets[acc_id] = acc_secrets.pop(orig)  # ID 改名，凭据随迁
            entry = acc_secrets.setdefault(acc_id, {})
            entry["fund_account"] = fund_account
            if passwords[i]:  # 留空 = 保持原密码不变
                entry["password_enc"] = encrypt_text(passwords[i])
            if not entry.get("fund_account") and not entry.get("password_enc"):
                acc_secrets.pop(acc_id, None)
        cfg["accounts"] = accounts
        save_yaml(cfg_path, cfg)
        save_yaml(sec_path, secrets)
        return redirect("/")

    @app.post("/delete")
    def delete_account():
        acc_id = request.form["delete_id"]
        cfg = load_yaml(cfg_path)
        cfg["accounts"] = [a for a in (cfg.get("accounts") or []) if a["id"] != acc_id]
        secrets = load_yaml(sec_path)
        (secrets.get("accounts_secrets") or {}).pop(acc_id, None)
        save_yaml(cfg_path, cfg)
        save_yaml(sec_path, secrets)
        return redirect("/")

    @app.post("/mode")
    def switch_mode():
        cfg = load_yaml(cfg_path)
        cfg.setdefault("execution", {})["mode"] = request.form["mode"]
        save_yaml(cfg_path, cfg)
        return redirect("/")

    return app


def main():
    app = create_app()
    print("管理界面已启动: http://127.0.0.1:8321 （仅本机可访问）")
    app.run(host="127.0.0.1", port=8321)


if __name__ == "__main__":
    main()
