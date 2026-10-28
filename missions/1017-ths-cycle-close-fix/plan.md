# Plan

1. [x] 读 AGENTS/INDEX/README/specs/config/MEMORY + 失败证据 runtime_data/ths_accounts/2026-10-17.json
2. [ ] RED：tests/test_client_lifecycle.py、test_ths_account_ui.py、test_ths_account_switch.py 增改断言，跑出失败
3. [ ] GREEN：
   - client_lifecycle：win32process.GetWindowThreadProcessId + 精确 PID WM_CLOSE
   - ths_account_ui：username 三级解析（可见文本/通用 token/命令行仅已知名）、close_main_window 非阻塞 WM_CLOSE、
     弹窗结构分类（委托下单登录框关后继续）
   - ths_account_switch：close_ths_client 等待退出弹窗→点“退出”→验证进程退出
4. [ ] 相关 tests → 全项目 pytest → 32 位导入（.venv32）
5. [ ] 真实只读探查：主窗控件/可见文本/命令行（只输出已知 username 匹配结果）
6. [ ] 真实温和关闭验证：close_ths_client + client_lifecycle._close_pid，确认 hexin/xiadan 无残留
7. [ ] 收尾：更新 mission 结果、MEMORY、INDEX（如有文件变动）

## 风险

- 真实控件类名未知 → 探查后按“全控件可见文本”兜底。
- 命令行可能含敏感哈希 → 只做已知 username 边界匹配，绝不回显原文。
- xiadan 关闭可能弹确认框 → 只允许精确按钮文本点击，绝不强杀。