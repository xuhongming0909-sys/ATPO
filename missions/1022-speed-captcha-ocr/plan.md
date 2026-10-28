# 计划

1. F8/中签/批量网格统一屏幕 OCR，单测证明不读取 `today_entrusts`。
2. 数字验证码登录与拷贝提示兜底，失败截图并停止当前操作。
3. 等待轮询提速 + 阶段耗时记录。
4. 全量测试。
5. dry-run GUI，再执行本轮 force-retry GUI 测试。


## 2026-10-22 进度

- F8/申购/中签网格改为屏幕 OCR，不再读取 `today_entrusts` 剪贴板。
- 数字验证码登录与拷贝提示兜底已实现。
- 登录窗账号下拉、登录按钮改窗口消息，减少鼠标依赖。
- pytest 311 passed；compileall 通过。
- GUI 外部 dry-run 已推进到登录阶段；Codex 非交互会话缺 active desktop/网络权限，最终实盘 GUI 需用户在桌面直接运行快捷方式验证。
