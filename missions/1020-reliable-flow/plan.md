# Mission 1020-reliable-flow Plan

## 总体步骤（用户指定顺序）
1. **Step 1 登录可靠性** ← 当前
2. Step 2 账户切换可靠性
3. Step 3 申购 → F8 确认 → 中签查询 → 推送全链路
每步真实生产验证通过后进下一步。

## Step 1 计划：登录可靠性

### 诊断（已完成）
真实失败记录（runtime_data/ths_accounts/2026-10-18.json, 2026-10-20.json）：
- OCR 子进程识别当前 username 不唯一/失败 → 整个账户 failed
- 主窗识别匹配 0 个 → 中途"找不到 hexin 主客户端窗口"
- xiadan 句柄失效后无恢复路径

### 改动方案（待用户确认）
1. **主窗识别加固**：窗口查找失败时重新枚举 + 按 PID 归属过滤，最多 2 次快速重试（间隔 ≤ 3s），仍失败 → 截图 + fail 该账户，不阻塞其他账户。
2. **OCR 兜底降级**：OCR 不唯一时，先用命令行 username 边界匹配 / 窗口控件文本兜底；只有全部失败才标 OCR_UNMATCHED。
3. **有界重试 + 计时**：每账户 login 阶段硬上限 90s，整体 15min；耗时写结果 JSON（新增 `durations` 字段）和回执。
4. **关客户端验证**：每次运行结束核对 lifecycle_close.closed_pids 非空且 residual 为空。

### 验证
- `python -m pytest -q` 全绿（新增：窗口重枚举重试、OCR 降级、超时中断的 mock 测试）
- 真实 `run.py ths-cycle --phase login`：两个 THS 账户（mx_525378109 / mx_mbqdpecj9）全部 ready 或明确弹窗跳过，耗时落盘，结束后 hexin 进程被温和关闭
- 验证时电脑可用性：全程 ≤ 15 分钟，失败快速退出

### 结果
Step 1 登录已完成真实验证（见 MEMORY 2026-10-20 条目）。Step 2 切换待做。

### 风险与遗留
- 蔡*良（华宝）需人工签可转债协议，属预期 dialog_required，不算失败
- 真实验证需用户不操作电脑约 5-15 分钟
