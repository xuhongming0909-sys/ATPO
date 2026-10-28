# AI-SUMMARY: 探针 3——WM_COMMAND 消息复制验证（走生产 query_allotment）
import json
import sys

sys.path.insert(0, r"C:\Users\93724\Desktop\自动打新")

from shared.config import load_config
from execution.client_registry import ClientSpec
from execution.ths_account_config import load_ths_account_mode, read_ths_password
from execution.ths_account_runner import GentleClientLifecycle
from execution.ths_account_ui import ThsAccountUI
from execution.ths_account_switch import ThsLoginAccount, switch_ths_account
from execution.ths_client import connect
from execution.allotment import query_allotment

out = {}
cfg = load_config()
mode = load_ths_account_mode(cfg)
accounts = [a for a in mode.accounts if a.enabled]
client = ClientSpec(client_id="ths_account_switch", hexin_path=mode.hexin_path, xiadan_path=mode.xiadan_path)

lifecycle = GentleClientLifecycle(client, cfg)
lifecycle.start()
try:
    ui = ThsAccountUI(client, cfg, known_ths_accounts=[a.username for a in accounts])
    switch_ths_account(ThsLoginAccount(username=accounts[0].username), client,
                       lambda: read_ths_password(accounts[0].username), ui, 120)
    refs = ui.discover_fund_accounts()
    first = next(r for r in refs if r.row_kind == "direct")
    ui.login_fund_account(first)
    user = connect(client=client)
    rows = query_allotment(user)
    out["row_count"] = len(rows)
    out["first_rows"] = rows[:3]
finally:
    lifecycle.close()
print(json.dumps(out, ensure_ascii=False, indent=2))
