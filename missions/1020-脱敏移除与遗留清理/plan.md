# Plan（已完结）

- [x] 1. 乱码：run32.cmd ?????? → chcp 65001 + UTF-8 BOM 重写；全仓库扫描仅此一处；删根目录垃圾 390/720
- [x] 2. 删 dual_client：gui_runner/discovery/preflight/boot_login/legacy_login_dialog/account_scope + tests；config clients/client_order/active_mode；register_tasks.ps1 只注册 ths-cycle
- [x] 3. 事故恢复：误删未入 git 的 hexin_login/login/window_scope/account_session → 从 ~/.codex 历史会话 dump + __pycache__ pyc 函数清单比对恢复；hexin_login 与 pyc 完全一致；login/window_scope 补齐缺失私有函数
- [x] 4. 非交易日门：data_fetch/trading_days.py（东财上证日K线+缓存+周末否决）→ run.py daily-report / catch_up / run_ths_cycle 全过门；真实验证 周三/周一=True 周六/国庆=False；daily-report 非交易日实跳
- [x] 5. 去脱敏：errors.py/task_state.py 仅排除凭据；account_identity.py 全量；switch 模块 masked 字段仅作内部匹配
- [x] 6. 推送重做：时间+账户（显示名+完整资金账号+THS 用户名）+事件，标题含 HH:MM；真实渲染验证通过
- [x] 7. 清理：tests/debug、恢复临时文件、_dpapi_check/ManagedClient 等死代码
- [x] 8. 测试：283 passed（重写 test_subscribe/test_client_lifecycle/test_catchup/test_receipts/test_cli，更新 test_task_state/test_notification_redaction/test_doctor_package/test_ipo_page）
- [x] 9. 文档：specs 全部、INDEX、README、逻辑图.MD、MEMORY 同步
- [x] 10. 终验：pytest 283 passed + 64/32 compileall OK + schedule-json OK + doctor ok

## 结果
- 净变化：execution 从 23 个文件减到 17 个；tests 从 37 个减到 25 个
- 风险：login.py/window_scope.py 为恢复+补写版本（4+1 个私有函数按接口约定重写），未经真机回归 → 下一交易日 dry_run 复核（逻辑图 §7-R1）
