# Mission 1020-reliable-flow Spec

## 任务类型
实现（可靠性改造 + 真实生产验证）

## 背景：真实失败证据（runtime_data/ths_accounts/*.json）
- `THS_ACCOUNT_MENU_READ_FAILED`：读账户下拉失败（2026-10-20，mx_525378109）
- `THS_CURRENT_ACCOUNT_OCR_UNMATCHED`：OCR 无法唯一识别当前 username（2026-10-18）
- `XIADAN_MISSING`：切换后 xiadan 窗口句柄失效（Handle is not a valid window handle）
- `FUND_ACCOUNT_CLICK_FAILED`：跑到一半"找不到 hexin 主客户端窗口"（窗口识别中途丢失）
- `THS_MAIN_WINDOW_NOT_UNIQUE`：主窗识别匹配 0 个
- 共同根因方向：主窗口/控件识别依赖 OCR + 模糊匹配，状态判断散落多处，重试无硬上限

## 目标
按用户指定顺序逐步修复并真实验证：
1. 登录可靠性（hexin 主界面 + 资金户直登）
2. 账户切换可靠性
3. 申购 → 确认（F8 核验）→ 中签查询 → 推送
每步真实生产场景跑通后再进下一步。

## 硬性约束（用户明确要求）
- 每阶段计时并落盘：每个账户、每个阶段的耗时写入结果 JSON 和回执。
- 时间硬上限：单账户单阶段 ≤ 90 秒；单次整体运行 ≤ 15 分钟，超时立即停止并关客户端。
- 重试有界：同一操作最多快速重试 2 次（总等待 ≤ 30 秒），仍失败则截图留证、标记 failed、跳过，绝不无限重试。
- 任务结束必须温和关闭同花顺（已有 client_lifecycle，需验证真实生效）。
- GUI 占用期间用户无法正常用电脑 → 宁可 fail-fast 也不长时间卡住。

## 范围（Step 1：登录）
- 输入：config 中启用的 THS 登录账户列表、secrets 中 DPAPI 密码
- 输出：每账户 login_status（ready/dialog_required/failed）+ 耗时 + 结构化 error_code + 截图证据
- 边界：不做申购；密码/验证码/协议类弹窗不自动绕过，标记后跳过
- 错误处理：窗口识别失败 → 重读窗口 → 重试 ≤ 2 → 截图 fail；OCR 不唯一 → 用窗口控件文本兜底，仍不唯一则 fail 该账户

## 对正式 spec 的影响
- 待 Step 1 方案确认后更新 `specs/execution.md`（重试上限、计时、fail-fast 规则）

## 步骤顺序
Step 1 登录 → 真实验证 → Step 2 切换 → 真实验证 → Step 3 申购/确认/中签/推送全链路 dry-run → 真实交易日验证
