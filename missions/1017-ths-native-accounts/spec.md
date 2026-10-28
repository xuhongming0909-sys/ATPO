# Mission Spec

## 任务类型
需求审查 + 账户模型调整（等待用户确认后实施）

## 目标
把账户运行模型改成“同花顺已登录账户原生发现”：不再依赖 WebUI、自定义 id、别称、配置权限；保证双客户端申购与推送准确。

## 范围
- 审查 `execution/`、`notification/`、`scheduler/`、`shared/`、`run.py`、`config/`。
- 计划更新正式 spec：`specs/spec.md`、`requirements.md`、`execution.md`、`security.md`、`operations.md`、`portability.md`。
- 计划移除 WebUI 入口和账户控制面板运行依赖；保留必要迁移说明。
- 计划重写账户身份：客户端显示名是唯一用户可见身份；完整资金账号不落盘、不进日志/推送，仅运行时哈希防重复。
- 申购范围只由当日日历、全局 blacklist、券商额度/拒绝结果决定；不按本地 permissions 过滤。

## 约束
- 先输出实施 spec，未经用户明确确认不得改正式 spec 或代码。
- `execution/` 测试只用 mock/桩对象，禁止真实登录、申购、推送。
- 不放宽 `execution.mode=live` 与 `--live` 双确认，不写入任何券商密码、资金账号原文、SendKey。
- 保持 UI 数据连续性；不可用账户必须报告 `failed`/`skipped`，不得假成功。
- 遵循 TDD：RED → GREEN → REFACTOR；代码文件不超 1000 行；核心文件维护 `AI-SUMMARY`。

## 对正式 spec 的影响
确认后更新 `specs/spec.md`、`specs/requirements.md`、`specs/execution.md`、`specs/security.md`、`specs/operations.md`、`specs/portability.md`，并同步 `INDEX.md`、`MEMORY.md`。

