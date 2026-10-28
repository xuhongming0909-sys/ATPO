# Mission Plan

## 目标

按 10-28 审查建议实施修复：企业微信兜底通道、健康自检日结、回执失败补发、runtime_data 清理、task_state 修剪、缴款截止提醒明示。

## 步骤与验证

1. RED：先写 wecom/channels/health/housekeeping/task_state.prune/receipts 截止文案/CLI schedule 键测试，验证 pytest 失败
2. GREEN：实现 notification/wecom.py、notification/channels.py、scheduler/health.py、scheduler/housekeeping.py、task_state.prune、run.py CLI、register_tasks.ps1、config，验证 pytest 全绿
3. 真实验证：python run.py schedule-json / health-check（真推企业微信）/ housekeep
4. 重注册计划任务 AutoIPO-HealthCheck（schtasks）
5. 同步 INDEX.md、逻辑图.MD、specs/operations.md、specs/notification.md、README、MEMORY

## 暂缓（push back 已说明）

- P1-6 代码拆分：文件未超 1000 行红线；GUI 模块拆分需真机回归，待 10-29 交易日验证后单独 mission。
- P2-9 验证码真弹窗补验：需真实触发，无法合成；保持观察项。

## 风险与回滚

- housekeep 只删 runtime_data 顶层已知垃圾后缀（路径守卫）；task_state 修剪归档不物理删除；出错恢复 archive 文件即可。
- 计划任务注册失败回滚：register_tasks.ps1 -Force 幂等，可重跑旧版本任务仍在。
