# Mission Spec

## 任务类型
修复

## 目标
让单个同花顺实例稳定登录启用且券商匹配的账户；当前验收只跑 8 个平安证券账户，中信建投/华宝暂不参与，并在委托下单界面逐户验证可识别、可切换；本阶段不提交任何委托。

## 范围
- 修改 `execution/hexin_login.py`：主界面账户菜单定位、逐户点击、错位识别。
- 修改 `execution/login.py`：统一账户会话状态、脱敏缓存、资金账号验证。
- 修改 `execution/boot_login.py`：主界面登录 → F12 委托界面 → 10 户会话校验。
- 修改 `config/config.yaml`：集中 GUI 登录参数。
- 修改 `tests/test_hexin_login.py`、`tests/test_boot_login.py`，新增会话状态和幂等测试。
- 更新 `specs/execution.md` 与 `specs/spec.md` 的登录链路描述。
- 不处理申购下单、中签查询、双同花顺实例、20 账户扩展。

## 约束
- 不填写交易密码、不绕过验证码；出现密码/验证码对话框立即停止并报告。
- 单实例上限 10 户。
- 不把完整资金账号写入 `runtime_data/` 或日志；完整账号只存 `config/secrets.yaml`。
- 不提交任何真实委托。
- 保留 `menu_row` 作为缓存/兜底，但不能成为唯一识别依据。
- 执行端必须使用 32 位 Python 环境，先做导入预检。

## 对正式 spec 的影响
更新 `specs/execution.md` 的“登录/换户模式”和 `specs/spec.md` 的 BootLogin 逻辑图，明确名称/缓存/最终资金账号三重校验。
