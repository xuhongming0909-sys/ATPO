# AI-SUMMARY: 探针 5——登录弹窗可能属 xiadan 进程；扫描 hexin+xiadan 全部窗口+全屏截图
import json
import sys
import time

sys.path.insert(0, r"C:\Users\93724\Desktop\自动打新")

from shared.config import load_config
from execution.client_registry import ClientSpec
from execution.ths_account_config import load_ths_account_mode, read_ths_password
from execution.ths_account_runner import GentleClientLifecycle
from execution.ths_account_ui import ThsAccountUI
from execution.ths_account_switch import ThsLoginAccount, switch_ths_account

out = {}
cfg = load_config()
mode = load_ths_account_mode(cfg)
accounts = [a for a in mode.accounts if a.enabled]
client = ClientSpec(client_id="ths_account_switch", hexin_path=mode.hexin_path, xiadan_path=mode.xiadan_path)

lifecycle = GentleClientLifecycle(client, cfg)
lifecycle.start()
try:
    ui = ThsAccountUI(client, cfg, known_ths_accounts=[a.username for a in accounts])
    switch_ths_account(ThsLoginAccount(username="mx_mbqdpecj9"), client,
                       lambda: read_ths_password("mx_mbqdpecj9"), ui, 120)
    refs = ui.discover_fund_accounts()
    hb = next(r for r in refs if "华宝" in r.display_masked)
    clicked = ui._click_main_row(hb)
    out["clicked"] = clicked.get("text")
    time.sleep(3)

    import pywinauto
    import win32process
    from execution.hexin_login import _hexin_pids
    from execution.login import _xiadan_pids
    pids = _hexin_pids(client) | _xiadan_pids(client)
    wins = []
    for w in pywinauto.Desktop(backend="win32").windows():
        try:
            pid = w.process_id()
        except Exception:
            continue
        if pid not in pids:
            continue
        try:
            edits = w.descendants(class_name="Edit")
            buttons = w.descendants(class_name="Button")
            wins.append({
                "pid": pid,
                "title": (w.window_text() or "")[:30],
                "class": w.class_name(),
                "rect": str(w.rectangle()),
                "visible": bool(w.is_visible()),
                "edits": [{"id": e.control_id(), "rect": str(e.rectangle())} for e in edits],
                "buttons": [{"id": b.control_id(), "text": (b.window_text() or "")[:10]} for b in buttons],
                "statics": [{"id": s.control_id(), "text": (s.window_text() or "")[:15], "rect": str(s.rectangle())}
                            for s in w.descendants(class_name="Static")][:12],
            })
        except Exception:
            continue
    out["windows"] = wins
    from PIL import ImageGrab
    path = r"C:\Users\93724\Desktop\自动打新\runtime_data\debug\captcha_screen.png"
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ImageGrab.grab().save(path)
    out["screenshot"] = path
finally:
    lifecycle.close()
print(json.dumps(out, ensure_ascii=False, indent=2))
