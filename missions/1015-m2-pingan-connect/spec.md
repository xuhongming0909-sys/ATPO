# Mission 1015-m2-pingan-connect — Spec

## 任务类型
实现（M2 第一阶段：连接验证）

## 目标
验证自动化库能连上已登录的同花顺下单客户端（xiadan.exe，平安证券账户），读取账户信息（资金/持仓快照）。验证标准：真实连接成功并返回真实账户数据（非空）。本阶段**只读**，不下单。

## 范围
- 新建：`execution/` 模块（同花顺客户端连接封装）
- 依赖：jqktrader（easytrader 的维护版继任者）
- 不碰：真实申购下单（下一阶段，先 dry_run）

## 约束
- AGENTS.md Constitution §9：本阶段只读操作；execution.mode 保持 dry_run
- 测试永不触碰真实客户端（用桩对象）
- 账户数据属敏感信息：验证结果只记录「能读到/字段非空」，不把资金数值写进任何文档/日志/推送

## 对正式 spec 的影响
- specs/requirements.md 里程碑 M2 进度
- 新建 specs/execution.md（连接方式、风险、dry_run 语义）
