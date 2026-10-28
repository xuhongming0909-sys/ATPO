# Mission Spec

## 任务类型

分析（流程审查与改进建议）

## 目标

基于当前代码、配置、task_state 真实运行数据与 MEMORY 历史故障，输出按优先级排序的全项目流程改进建议。

## 范围

scheduler 编排、execution 生命周期、notification 通道、runtime_data/task_state 卫生、监控闭环、文档同步。

## 约束

- 只读分析，不改业务代码、配置、计划任务。
- 建议必须有真实证据（文件/状态/历史记录）支撑，不臆测。

## 对正式 spec 的影响

无；后续若采纳某条建议，再按 Formal Spec Rules 先改 spec。
