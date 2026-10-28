# Mission Spec：登录回执动态账户计数与身份识别

## 任务类型
修复 + 需求更新

## 目标
登录回执按唯一资金账户动态计数，标题和正文能明确识别具体 THS 账户与资金账户；新增账户后重新完成真实登录和完整流程验收。

## 范围
- `scheduler/catchup.py`
- `notification/receipts.py`
- `execution/ths_account_runner.py`
- `shared/errors.py`
- `shared/task_state.py`
- `tests/test_receipts.py`
- `tests/test_catchup.py`
- `tests/test_ths_account_runner.py`
- `tests/test_notification_redaction.py`
- `config/config.yaml`
- `config/config.example.yaml`
- `AGENTS.md`、`README.md`、`INDEX.md`
- `specs/security.md`、`specs/notification.md`、`specs/operations.md`

不碰：真实委托提交逻辑、双同花顺模式、20 户扩展、Web 管理界面。

## 约束
- execution 测试只用 mock/桩对象。
- 真实 GUI 验收只运行 login/all dry-run；不得提交真实委托。
- 账户总数只按唯一资金账户计算，不能用 THS 行数、重复行数或固定值。
- 项目仅用户本人本机使用；普通账户识别信息可进入本机日志和推送。
- 交易密码、验证码、SendKey、token、DPAPI 密文仍不得进入 git、日志或推送。
- 不使用强杀进程；预存在 `xiadan-plus.exe` 关闭失败只报告。

## 对正式 spec 的影响
先更新 `specs/spec.md`、`specs/security.md`、`specs/notification.md`、`specs/operations.md`，再改代码。