# Mission Spec

## 任务类型

修复

## 目标

修复 2026-10-28 全项目 review 中确认的 Critical、High、Medium 问题，并在不触发真实券商操作的前提下完成测试、编译、doctor 和静态验证。

## 范围

- 编排与状态：超时串行、中签查询状态、批量拒绝状态、all 阶段生命周期、错误 lifecycle。
- GUI 与数据：OCR 表头校验、F8 唯一委托核验、账户幂等键、交易日/节假日门、锁原子性。
- 安全与交付：回执递归脱敏、验证码截图留存、WebUI CSRF/依赖、打包排除、通知失败留痕。
- 工程卫生：1000 行限制、文档一致性、测试隔离、runtime_data 保留策略、根目录临时项。

## 输入

- 当前工作区最新源码与配置。
- `missions/1028-full-review/plan.md` 的 22 项结论。
- 现有测试、`task_state.json`、计划任务状态和本机环境检查结果。

## 输出

- 分批、可回滚的代码与文档修改。
- 每个行为修复对应回归测试。
- 64/32 位 compileall、隔离 pytest、doctor、CLI/schedule、依赖检查结果。
- 更新后的 mission、INDEX、逻辑图、spec、README 和 MEMORY 交接摘要。

## 边界

- 不启动真实券商客户端，不提交真实委托，不发送真实推送，不修改计划任务的触发时间。
- 验证码、密码、SendKey、DPAPI 密文不进入 Git、日志、状态或推送正文。
- runtime_data 清理采用归档优先；不删除有效订单台账、任务状态、实盘截图和诊断证据。
- `AGENTS.md` 与既有 templates 不修改。
- 大文件按职责拆分，保留必要兼容导出，避免一次性重构改变业务行为。

## 默认决策

- runtime_data 历史调试资料移动到 `archive/review-cleanup-20261028/`，不直接删除。
- WebUI 采用本进程随机 secret + CSRF token，仍只监听 `127.0.0.1`。
- 通知额度失败写入本机 outbox，后续运行自动补发；不新增无凭据的邮件通道。
- 当前、未来交易日使用本地官方交易日历配置判定；历史日继续用东财 K 线。
- 32 位环境保留 `pandas==2.0.3`，补装缺失的 `pyquery`/`pypiwin32` 并加兼容 smoke test；不降级到 pandas 1.5.3。

## 错误处理

- 任一 Critical 修复失败：停止后续批次，保留现场，不标记完成。
- 外部下载失败：记录真实错误，不伪造通过。
- 真实 GUI/实盘路径只能在用户桌面由用户显式执行；本次自动验证不触碰。

## 对正式 spec 的影响

需要先同步 `specs/spec.md`、`specs/execution.md`、`specs/operations.md`、`specs/security.md`、`specs/notification.md`、`specs/portability.md` 和 `逻辑图.MD`，再实现行为变化。

## 执行批次

1. P0：超时串行、中签状态、批量拒绝。
2. P1：OCR/F8、交易日、lifecycle、幂等键、锁。
3. 安全：回执脱敏、验证码截图、WebUI、通知 outbox。
4. 工程：打包、依赖、文件拆分、测试隔离、runtime_data 归档、文档。
