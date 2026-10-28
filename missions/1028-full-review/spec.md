# Mission Spec

## 任务类型

审查

## 目标

完成全项目静态审查、测试验证、配置与安全边界核对，输出按严重度排序、可追溯证据的完整 review 报告。

## 范围

入口、配置、spec、data_fetch、scheduler、execution、notification、shared、webui、tests、Windows 脚本和文档一致性。

## 约束

- 只读审查，不修改业务代码、配置、计划任务和运行数据。
- 不触发真实券商客户端、真实委托、真实推送或计划任务。
- 遵守 AGENTS.md 安全规则；不读取或展开 secrets.yaml 内容。
- 发现以代码真实行为为准，并核对 spec、逻辑图和 README 是否漂移。

## 对正式 spec 的影响

仅报告冲突与建议，不修改正式 spec。
