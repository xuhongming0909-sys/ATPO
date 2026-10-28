# Assistant Rules

Owner: user. AI must not modify this file without user's explicit approval.
本项目完全本机运行（Windows）：日历抓取、调度、券商客户端自动化、通知推送全部在本机完成，无服务器、无强制 git 工作流。

永远保持诚实，数据要准确无误。

## Purpose

本文件定义 AI 在本仓库内的稳定工作规则，只含两个顶级部分：

- `Workflow`：AI 如何读取、记录、同步、收尾工作
- `Constitution`：不应轻易违背的长期规则

# Workflow

## Local Workflow（最高优先级）

**本项目完全本机运行，无服务器、无强制 git 同步。**

1. 所有代码修改、配置变更、运行验证都在本机完成。
2. 定时调度使用 Windows 任务计划程序（`schtasks`），不用 cron/systemd。
3. 本地 git 仓库仅作历史留痕，可提交，但不作为强制工作流。
4. 券商密码等敏感信息只存本机，任何情况下不外传（见 Constitution §9）。

## Read Order

每个新会话开始，AI 必须按此顺序阅读：

1. 本文件（`AGENTS.md`）
2. `INDEX.md`（项目架构与文件索引）
3. `逻辑图.MD`（顶层目标-判定-链路控制图；代码改动影响链路/判定/不变量时必须同步）
4. `README.md`
5. `specs/spec.md`
6. 相关 `specs/*.md`
7. `config/config.yaml`
8. `MEMORY.md` 最新条目

## Formal Spec Rules

- `specs/spec.md` 是项目级地图与索引。
- `specs/*.md` 存放长期有效的模块/功能需求。
- 任务若改变正式需求，必须先更新 `specs/spec.md` 和受影响的 `specs/*.md`，再动手实现。
- 顶层 spec 与子 spec 不得存在冲突规则。
- 任何 markdown 文档不得超过 500 行，接近上限时拆分或压缩。

## Mission Rules

- 每个非聊天类 AI 任务必须创建 mission。
- 非聊天任务包括：实现、审查、分析、需求更新。
- 纯聊天、纯概念问答、低上下文闲聊不得创建 mission。
- Mission 目录：`missions/MMDD-short-name/`。
- 每个 mission 目录只含：`spec.md`（任务类型、目标、范围、约束、对正式 spec 的影响）和 `plan.md`（步骤、验证、结果、风险）。
- 格式参考 `templates/`。`missions/` 只保留最近 30 个，更旧的直接删除。

## Memory Rules

- `MEMORY.md` 只保留最近 50 条。
- 每条保持简短，只服务交接。
- 只记录：决策、有意义的动作、验证结果、值得记住的失败、下一步。
- 不要把完整对话倒进 `MEMORY.md`。

## Config Rules

- 非敏感配置只放 `config/config.yaml`。
- 凭据只放 `config/secrets.yaml`（git 忽略）：SendKey 明文可放；**券商交易密码只能以 DPAPI 密文（password_enc）存放**，明文永不落盘。
- 本项目仅用户本人本机使用。THS 用户名、券商显示名、资金账号/尾号等普通账户识别信息可以进入本机日志、运行时结果和 Server酱推送，用于准确识别账户。
- 配置键统一 `snake_case`。
- markdown 文档中不得出现真实密钥或密码。

## Completion Rules

- 验证真实改动，不允许只改不验。
- 更新当前 mission 文件。
- 任务有交接价值时更新 `MEMORY.md`。
- 需求变更时先同步正式 specs。
- 新建/移动文件时更新 `INDEX.md`。
- 模块职责变化时同时更新模块 spec 和 `INDEX.md`。
- 代码改动改变目标链路、判定条件或不变量时，同步更新 `逻辑图.MD`（按其 §8 对照表逐节核对）。

## File Rules

### 根目录清洁

根目录只允许：
- **白名单文件**：README.md, AGENTS.md, INDEX.md, MEMORY.md, 逻辑图.MD, requirements.txt, run.py, .gitignore, .env.example, .editorconfig
- **允许的目录**：config, specs, missions, templates, shared, data_fetch, execution, notification, scheduler, webui, tests, runtime_data, archive, docs
- **禁止**在根目录放临时文件（截图、调试脚本、日志）

临时文件规则：
- 调试脚本 → `scripts/debug_scripts/`（本项目归入 `tests/debug/`）
- 日志/截图 → 运行时写入 `runtime_data/`

### 文件大小限制

任何代码文件（`.py`）不得超过 **1000 行**。超过必须按职责拆分，拆分后登记 INDEX.md。

### AI-SUMMARY 规范

每份核心代码文件顶部必须有 `AI-SUMMARY:` 注释：

```python
# AI-SUMMARY: [一句话职责描述]
```

修改文件后同步更新 INDEX.md 中的文件摘要索引。

## TDD 工作流

实现功能或修复 bug 必须遵循三环循环：

```
RED   → 写一个测试描述一个行为 → 测试失败
GREEN → 写最小代码让测试通过
REFACTOR → 重构消除重复
```

- 垂直切片：每次只写一个测试，只写刚好通过它的代码。
- 测试验证公开行为而非实现细节。
- **永远不要在 RED 状态下重构**。
- 实盘交易相关代码（execution/）的测试必须用模拟/桩对象，测试永不触碰真实券商客户端。

# Constitution

## 1. Think Before Coding
不假设、不藏疑惑。存在多种合理解释时列出来，不替用户沉默决策。关键点不清楚就停下来问。

## 2. Simplicity First
用能解决问题的最小代码。不加未被要求的功能、抽象、配置项、错误处理。50 行能解决就不写 200 行。

## 3. Surgical Changes
只改与当前任务直接相关的部分。不顺手"优化"无关代码。自己改动产生的孤儿代码自己清理。

## 4. Goal-Driven Execution
每个任务动手前定义可验证的成功标准，多步任务拆成带验证的短步骤。

## 5. Truth First
永远优先真实数据、真实接口、真实文件、真实输出。拿不到真实输入就明确暴露限制，不用假数据冒充真实结果。

## 6. Execute Directly
用户不是程序员。AI 能独立分析、修改、配置、运行、验证的就直接做。只在权限、密钥、账号、人工判断、外部资源确实需要时才请用户介入。

## 7. Separate Architecture
不同职责保持分离，禁止跨模块私相耦合：

- `data_fetch/` = 打新日历等数据抓取 + 规范化
- `scheduler/` = 定时任务编排
- `execution/` = 券商客户端自动化（仅本机运行）
- `notification/` = 推送通道（Server酱/邮件）
- `shared/` = 配置、路径、时间、运行时状态、公共工具
- 跨域逻辑下沉到 `shared/`，不允许模块间直接私下耦合（避免参数耦合）

## 8. Centralize Configuration
所有长期存在、影响行为的参数必须进 `config/config.yaml` 统一入口。禁止在多处长期硬编码路径、阈值、开关、URL、账号字段。先加配置，再写实现。

## 9. Security First（本项目特有，不可违背）

- 本项目仅用户本人本机使用。THS 用户名、券商显示名、资金账号、资金账号尾号等普通账户识别信息可以进入本机日志、运行时结果和 Server酱推送，必须足以定位具体账户。
- 交易密码、验证码、SendKey、token、DPAPI 密文等凭据**永不进 git、永不进日志、永不进推送消息正文**。
- 券商交易密码以 DPAPI 密文存 `config/secrets.yaml`（绑定本机当前 Windows 用户，他机/他人解不开），由 `shared/credstore.py` 加解密；表单密码框留空=保持不变。
- `execution.mode` 默认 `dry_run`；实盘交易必须在 config 显式改为 `live` 且经用户确认。
- 每次实盘申购/查询操作必须留痕：操作日志 + 客户端截图存档到 `runtime_data/`。
- 本工具仅限自用，禁止扩展为面向他人的代操作服务。

## 10. User Ownership
本文件（`AGENTS.md`）与 `templates/` 下已有模板归用户所有，AI 不得修改；只能提议变更。AI 可以新增模板。

## 11. Documentation Language
非代码文档使用中文；核心逻辑代码注释使用中文。

## 12. Verification Before Done
改完代码不跑验证就不许说"修好了"。验证三层：能导入 → 真实调用拿到输出 → 关键字段非空且符合预期。验证结果附在回复中。
