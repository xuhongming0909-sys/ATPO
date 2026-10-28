# Mission Plan

## 步骤
1. 更新正式 spec：动态账户范围、实盘幂等、preflight、调度约束。
   验证：重读 specs/spec.md、specs/execution.md、specs/security.md，无规则冲突。
2. 先为动态账户选择、订单台账、时段保护写失败测试。
   验证：`python -m pytest -q` 新测试 RED。
3. 实现动态账户匹配：按当前菜单/委托账户列表选择，不按券商或固定 ID 过滤。
   验证：换成另一组 10 个模拟账户仍全部匹配；华宝/中信建投不在白名单约束中。
4. 实现实盘订单台账和单次提交保护。
   验证：重复运行新增委托为 0；unknown/submitted_unverified 不重试。
5. 批量申购改为 F8 逐笔核验，弹窗 success 不单独判成功。
   验证：查到委托=提交成功；查询失败=未核验并阻断重试。
6. 修复计划任务并增加 preflight、申购时段保护。
   验证：任务动作无 cmd 引号问题；preflight 只读；时段外 live 不下单。
7. 跑全量测试、32 位导入检查和真实只读 preflight。
   验证：测试全过；导入 ok；当前客户端实际账户集合可动态识别；无真实委托。

## 验证结果
- 初始 RED：新增动态账户、订单台账、时段保护测试按预期失败（模块尚未实现）。
- GREEN：新增模块和实现后，相关测试通过；批量申购测试确认弹窗 success 不能单独判成功。
- `python -m pytest -q`：76 passed。
- `tests/test_hexin_login.py`：重复测试名已消除，当前测试名无重复。
- 32 位导入：Python 3.11.9 / 32-bit；pywinauto、win32gui、jqktrader、numpy、pandas、cv2 全部 ok。
- 真实只读 `run.py preflight`：ok=true；当前 xiadan 动态识别到 8 个平安账户，8/8 ready；只输出哈希/脱敏资金账号。
- 真实只读 `run.py boot-login`：当前菜单匹配 10 个配置账户，8/10 ready；中信建投/华宝两户周末登录失败，未被排除，后续客户端可登录时会重新参与。
- 菜单文本可读时按名称动态匹配；文本不可读时才使用坐标兜底，并记录实际点击行。
- Windows 计划任务已重建：5 个任务均通过 `scheduler/run32.cmd` / `run64.cmd` 直接调用，工作目录正确、StartWhenAvailable=true、允许电池启动；BootLogin 原错误引号已消失。
- 东财周末空结果按 `code=9201/查询数据为空` 处理为合法空日历；其他 success=false 仍报错。包装脚本 `run64.cmd calendar` 实测退出 0。

## 结果
动态账户范围、单次提交台账、批量 F8 核验、实盘时段保护、preflight 和 Windows 任务修复已完成。当前外部限制仅为周末中信建投/华宝无法登录；代码不再按券商排除账户。

## 风险与遗留
- 同花顺 GUI 仍依赖交互桌面，锁屏不可运行。
- 单实例上限 10；双实例和 20 户不在本任务范围。
- 券商无官方 API，客户端升级仍可能破坏控件定位。
- 中签通知去重和更长周期的真实实盘回归仍需后续交易日观察。
