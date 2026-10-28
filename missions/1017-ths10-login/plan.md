# Mission Plan

## 步骤
1. 建立任务、更新正式登录规格。
   验证：重新读取 `specs/execution.md`、`specs/spec.md`，确认登录链路与本任务一致。
2. 先写模拟菜单/会话测试并确认 RED。
   验证：`python -m pytest -q tests/test_hexin_login.py tests/test_boot_login.py` 中新增测试失败。
3. 实现主界面菜单名称/缓存/坐标兜底，加入点击结果状态。
   验证：新增单元测试通过，旧行为测试不回归。
4. 实现脱敏账户会话缓存和资金账号哈希校验。
   验证：测试确认缓存不含完整资金账号，目标账户匹配正确。
5. 重构 BootLogin 流程：主界面 10 户 → F12 → xiadan 逐户切换验证。
   验证：模拟测试覆盖 10/10、错位、密码弹窗、xiadan 缺户、重复运行。
6. 修复 32 位依赖并做导入预检。
   验证：`.venv32\Scripts\python.exe -c "import pywinauto, win32gui, jqktrader; print('ok')"` 成功。
7. 真实只读验收，不下单。
   验证：运行 `run.py boot-login`，检查结果、截图、日志；确认没有委托操作。

## 验证结果
- `python -m pytest -q`：54 passed。
- `.venv32\Scripts\python.exe -c "import pywinauto, win32gui, jqktrader; print('ok')"`：ok；numpy 1.26.4 / pandas 2.0.3 / opencv 4.10.0。
- `runtime_data/account_map.json`：version=2、10 条脱敏缓存、完整资金账号键 0 条。
- 真实只读 `run.py boot-login`：按“下拉→点第1户→重新下拉→点第2户”完成 8 个平安证券账户登录，F12 后逐户复核，8/8 ready；日志 `runtime_data/boot-login-pingan8-2026-10-17.log`。
- 32 位依赖导入复查通过；`runtime_data/results/` 无本次新增委托结果，boot-login 全程无委托提交。

## 结果
8 个平安证券账户登录链路真实验收通过。中信建投/华宝两户按用户要求暂不参与；下一阶段再扩展其他券商。

## 风险与遗留
- 同花顺账户菜单是 owner-drawn，UIA 可能读不到行文本；实现保留坐标兜底并通过 xiadan 账户列表/资金账号最终校验。
- 客户端弹出密码或验证码时无法安全自动化，必须人工处理。
- 本次只验证单实例 8 个平安账户，不代表其他券商、20 户或双实例可行。
