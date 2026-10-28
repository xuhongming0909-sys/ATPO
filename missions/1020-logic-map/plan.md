# Mission Plan — 1020-logic-map

## 步骤
1. 按 Read Order 读取项目文档（AGENTS/INDEX/README/spec/config/MEMORY）→ 已读，确认当前模式与缺口
2. 写 `逻辑图.MD`（9 节 + Gate 总表 + 变更同步对照表）→ 验证：行数 ≤500
3. 写 `templates/logic-map-template.md`（模板 + §C 核对清单）→ 验证：行数 ≤500
4. 嵌入 AGENTS.md：Read Order 第 3 项、Completion Rules 1 条、白名单 1 项 → 验证：Select-String 回显
5. INDEX.md 加文件索引 + templates 节；README 文档导航加行；specs/spec.md 加指针行 → 验证：回显
6. 记 MEMORY.md

## 验证结果
- `逻辑图.MD`：149 行（≤500）；`logic-map-template.md`：80 行。
- AGENTS.md：行 31–38 Read Order 为 1–8 连续编号，含"逻辑图.MD（顶层目标-判定-链路控制图…）"；行 78 新增同步规则；行 85 白名单含 逻辑图.MD。
- INDEX.md：文件索引含 逻辑图.MD 行（172 行，≤500）；新增 templates/ 节。
- README.md：文档导航含"顶层逻辑图（目标→判定→链路控制）：逻辑图.MD"。
- specs/spec.md：全局规则摘要末加指针行。
- 无 .py 改动。
- 收尾时发现并行会话已修复 K1/K2/K3/K5 部分并改回执格式，逻辑图 §7 快照已同步更新（K1–K3 闭环、K5 部分闭环、K4 遗留）。

## 结果
完成。证据见上"验证结果"。

## 风险与遗留
- 风险：`specs/spec.md` 内"系统逻辑图"节与根目录 `逻辑图.MD` 存在内容重叠；当前约定：spec.md 节偏"链路细节快照"，逻辑图偏"目标-判定-控制中枢"，冲突时以代码为准修逻辑图（模板 §9 已写明）。
- 下一步：后续每次代码改动按逻辑图 §8 对照表同步；K1–K5 修复后更新 §7 快照。