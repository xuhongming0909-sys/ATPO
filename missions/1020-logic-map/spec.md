# Mission Spec — 1020-logic-map

## 任务类型
需求更新 / 文档实现

## 目标
新增顶层控制图 `逻辑图.MD`：总目标→目标分解(G0–G6)→判定门(Gate)总表→主链路决策流程图→状态机→不变量→当前状态快照→变更同步对照表，并沉淀模板 `templates/logic-map-template.md`，嵌入 AGENTS.md Read Order / Completion Rules / 白名单，挂接 INDEX.md、README.md、specs/spec.md。

## 范围
- 新增：根目录 `逻辑图.MD`、`templates/logic-map-template.md`、`missions/1020-logic-map/`
- 修改：`AGENTS.md`（Read Order 插入第 3 项、Completion Rules 加 1 条、白名单加 1 项）、`INDEX.md`、`README.md`（文档导航）、`specs/spec.md`（全局规则摘要加 1 行）、`MEMORY.md`
- 不碰：任何 `.py`、config、templates 已有模板（mission-spec/plan）

## 约束
- AGENTS.md §10：AGENTS.md 需用户显式批准才改 — 用户本轮指令"嵌入顶层设计中例如 agent.MD"即显式批准，仅做最小插入。
- 逻辑图内容必须反映当前真实代码/配置/MEMORY 状态（ths_account_switch、live、5 计划任务、K1–K5 缺口）。
- 中文文档；单文件 ≤500 行。

## 对正式 spec 的影响
- `specs/spec.md` 全局规则摘要加一行指针，不改既有规则；spec.md 内"系统逻辑图"节保留（更细的链路），无冲突。