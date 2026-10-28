# Mission Spec — THS 独立会话与操作信息完整化

## 任务类型

bugfix + requirement update（TDD）

## 目标

1. `ths_account_switch` 按每个同花顺登录账户独立启动、登录、处理资金账户、执行阶段、温和关闭。
2. 登录切换失败必须记 `switch_failed`，身份上下文不一致记 `wrong_account`，不误报成功。
3. 密码框元数据允许缺少 Win32 handle/control_id，凭 style/password_hint/rectangle 唯一识别；绝不读取 Edit 文本。
4. 日志、状态和回执显示完整 THS 用户名、账户显示名、状态、错误和业务明细；密码、验证码、SendKey、完整资金账号等核心凭据仍排除。
5. 资金账户点击后不发送 ESC、完整等待登录弹窗；目标未进入 xiadan 时明确记 `not_logged_in`，不误报 `switch_failed`。

## 范围

- `execution/ths_account_switch.py`
- `execution/ths_account_ui.py`
- `execution/ths_account_windows.py`
- `execution/ths_account_runner.py`
- `shared/task_state.py`
- `shared/errors.py`
- `notification/receipts.py`
- 对应测试、README、INDEX、specs。

## 约束

- execution 测试全 mock，不触碰真实券商客户端。
- 不修改 `AGENTS.md`、`templates/`、`config/secrets.yaml`。
- 不提交真实委托。

## 对正式 spec 的影响

同步 `specs/ths-account-switch.md`、`specs/execution.md`、`specs/operations.md`、`specs/notification.md`、`specs/requirements.md`。
