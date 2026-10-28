# Mission 1015-m2-pingan-connect — Plan

## 步骤
1. 安装 jqktrader + pywin32
2. 确认 xiadan.exe 处于已登录状态（用户已完成平安账户登录）
3. 编写 execution/ths_client.py 连接封装（路径进 config）
4. 真实连接：读资金/持仓，验证字段非空
5. 记录结果，写 specs/execution.md

## 验证结果
- 32 位 Python 3.11.9 + jqktrader + pandas 2.0.3 + numpy 1.26.4 环境就绪（.venv32）
- **真实连接成功**：jqktrader 连上已登录的平安证券 xiadan 客户端，balance 返回 dict（资金余额/可用金额/股票市值/总资产字段齐全且非空），position 返回 list 非空
- 敏感数值未写入任何文档/日志/git

## 结果
完成（M2 第一阶段：连接与只读验证）。

## 风险与遗留
- connect() 可能重启 xiadan 进程，登录态靠客户端「记住密码/自动登录」保持；用户需确认勾选了自动登录。
- 下一阶段（M2 第二阶段）：dry_run 申购流程——读当日日历 → 生成申购指令 → 不实际下单，验证流程完整性；之后用户确认再实盘一单。
- 遗留清理：%LOCALAPPDATA%\Programs\Python\Python312-32 为中途误装版本，可删（约 150MB）。
