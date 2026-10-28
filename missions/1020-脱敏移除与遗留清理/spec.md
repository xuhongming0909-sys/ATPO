# Mission: 1020-脱敏移除与遗留清理
## 任务类型
重构 + 需求变更

## 目标
1. 修复项目乱码（编码统一 UTF-8）
2. 根源移除脱敏：推送/日志完整显示账户信息（时间+账户+事件）；仅保留密码/验证码/SendKey/token 凭据排除
3. 重做三类回执推送格式
4. 非交易日不启动任何任务（真实交易日历判定）
5. 删除 dual_client 双客户端遗留（代码/配置/计划任务/测试/文档）
6. 全项目清理无用代码与文件，spec 与代码保持一致

## 范围
run.py、execution/、scheduler/、notification/、shared/、data_fetch/、config/、tests/、specs/、INDEX.md、README.md、AGENTS.md、MEMORY.md

## 约束
- 单客户端 ths_account_switch 为唯一模式
- 凭据（密码/验证码/SendKey/token/DPAPI）仍不进日志/推送/git
- 实盘双保险 execution.mode=live + --live 不变
- 订单台账与不确定状态阻断不变
- TDD：改完跑全量 pytest

## 对正式 spec 的影响
spec.md / execution.md / operations.md / notification.md / security.md / requirements.md / portability.md / ths-account-switch.md / calendar.md 全部同步更新
