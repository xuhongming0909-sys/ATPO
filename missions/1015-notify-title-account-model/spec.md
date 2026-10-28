# Mission 1015-notify-title-account-model — Spec

## 任务类型
实现 + 需求更新

## 目标
1. 通知格式改进：微信通知列表只显示标题，**标题必须承载核心信息**（日期、只数、标的名称），正文放明细。验证：改后真实推送一条，手机上不点进去就能看到打了什么。
2. 账户模型扩展：accounts 增加 `note`（用户备注）、`account_type`（normal 普通 / credit 信用）、`bj_enabled`（北交所打新独立开关，默认 false）。北交所申购全额缴款、规则不同，必须每账户独立控制。
3. 雪球替代同花顺可行性调研结论归档（不可行，无公开 API）。
4. M3 需求补充：本地管理界面（Web 表单），用户不懂代码，需要图形化增删改账户、开关北交所，且无需手动操作同花顺（首次登录后由程序接管）。

## 范围
- 改：`scheduler/jobs.py`（标题格式）、`config/config.yaml`（账户字段）、`tests/test_report.py`
- 改 spec：`specs/notification.md`（标题规则）、`specs/requirements.md`（v3.1）、`specs/calendar.md`（市场覆盖确认）
- 不碰：execution/ 实现（M2）

## 约束
- TDD：先改测试再改实现
- 标题长度控制：Server酱标题过长会被截断，名称列表超阈值时折叠为「债N股M」
- 推送禁止出现敏感信息（不变）

## 对正式 spec 的影响
- specs/requirements.md → v3.1
- specs/notification.md 增加标题规则
- specs/calendar.md 记录市场类型覆盖验证结果
