# Mission Spec

## 任务类型
审查 / 分析

## 目标
审查当前代码与端到端运行逻辑，形成按 P0-P3 分级、可定位、可复现、可修复的审查结论；所有结论基于真实代码、真实测试或明确证据。

## 范围
- data_fetch、scheduler、execution、notification、shared、webui、run.py、tests。
- 覆盖数据抓取 -> 配置/凭据 -> Windows 计划任务 -> 登录/账户匹配 -> 申购/中签 -> 台账/截图 -> 推送的完整链路。
- 不修改生产代码、配置、正式 specs 和用户所有文件。

## 约束
- 只读审查；禁止真实登录、申购、下单、推送。
- 敏感信息不进入报告、日志或文档。
- 遵守 AGENTS.md Constitution §1-§12，尤其 Truth First、Security First、Surgical Changes、Verification Before Done。
- 输出必须带绝对路径、行号、触发条件、证据和最小修复建议。

## 对正式 spec 的影响
无。当前任务仅审查；若后续修复改变正式需求，必须先更新 specs/spec.md 与相关 specs/*.md。