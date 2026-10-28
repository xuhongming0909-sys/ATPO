# Mission Plan

1. [x] 停止旧 agents/ths-cycle 进程，确认无运行中任务。
2. [x] 全量测试基线：359 passed。
3. [x] RED：密码控件缺 handle/control_id、缺 style 时 password hint 识别；普通用户名/显示名不得被数字规则遮蔽。
4. [x] GREEN：密码元数据兼容稳定 rectangle/style/password_hint；回执输出完整普通操作信息。
5. [x] 全量回归：363 passed；64/32 compileall、32 位依赖导入、doctor ok、schedule-json 通过。
6. [x] 清理 `tests/debug/` 调试脚本和重复测试定义；拆分 `ths_account_model.py`、`ths_account_windows.py`，所有项目 Python 文件 ≤1000 行；更新 INDEX/mission/MEMORY。
7. [x] 生成项目包：`runtime_data/package/auto-ipo-clean.zip`，145 entries，排除 `.git`、`.venv32`、`runtime_data`、`config/secrets.yaml` 和缓存，脚本自检通过。
8. [x] 真实 login-only 复跑发现 `win32gui.GetWindowTextLengthW` 不存在；按真实 pywin32 API 改为 `GetWindowTextLength`，新增回归测试。
9. [x] 修复资金账户点击后立即发送 ESC、直登行只等 1 秒导致弹窗漏检；改为点击成功不关闭菜单、统一等待完整 `dialog_wait_s`。
10. [x] 目标账户点击后未进入 xiadan 时改记 `not_logged_in / fund_login_result`；实际登录弹窗标记 `login_required=true`；保留 `THS_PASSWORD_MISSING` 结构化错误码。
11. [x] 菜单账户行保留 UIA `top/bottom` 并点实际行中心；增加资金登录结果轮询参数，避免点击后过早判失败。
12. [x] xiadan 主窗不再因标题“委托下单”被误判为资金登录弹窗；登录窗仍按资金账号/证券公司+交易密码结构识别。
13. [x] 最终回归：370 passed；64/32 compileall、32 位依赖导入、doctor、schedule-json、项目包自检全部通过。
14. [x] 真机诊断：记录主菜单真实行边界、xiadan ComboBox 条目和资金账户点击结果。
15. [x] RED：登录窗口 username 不得被当作同花顺主窗；stale 错误必须带具体阶段。
16. [x] GREEN：主窗存在性独立判断，验证阶段只读主窗账户名；按阶段包装 GUI stale。
17. [x] 真实 GUI 只跑 login，验收第一户 8 ready + 1 明确失败、第二户 4 ready。

## 真实 GUI 验收（2026-10-18）

- 命令：`python run.py ths-cycle --date 2026-10-18 --phase login`。
- `mx_525378109`：8 个资金账户 `ready`；中信建投资金登录弹窗 `dialog_closed`。
- `mx_mbqdpecj9`：`switch_status=switched`，4 个资金账户 `ready`；另 1 个中信建投资金登录弹窗 `dialog_closed`。
- `python -m pytest -q`：392 passed；64/32 位 compileall 通过。
- 仅执行登录阶段，没有提交申购或中签操作。

## 验证标准

- `python -m pytest -q` 全绿。
- `python run.py doctor` 正常。
- `python run.py ths-cycle --date 2026-10-18 --phase login` 保持登录-only；真实 GUI 验收已完成，不提交委托。
- 回执包含 `mx_525378109`、账户显示名、状态和错误原因，不包含密码、验证码、SendKey、完整资金账号。

## 风险

- 同花顺自绘控件仍可能不提供任何 password hint；此时明确报 `THS_PASSWORD_CONTROL_NOT_FOUND`，不盲选普通 Edit。
- 真实 GUI 的账号切换需在可登录时段验证；单元测试不替代真实验收。
- DPAPI 密码密文仍可选；本次客户端保存密码登录成功。两组均各有 1 个中信建投资金登录弹窗，按设计关闭并记录 `dialog_closed`，不得伪造成功。
