# 计划

1. 诊断周五未触发根因 → 完成：任务定义正确但 PC 睡眠无 WakeToRun；注册脚本尾部语法错误使重注册失败。
2. 修 register_tasks.ps1 + 重注册 + 验证 XML WakeToRun=true。
3. 电源唤醒定时器 AC/DC=1；启用 TaskScheduler/Operational 日志。
4. 一键打新弹窗处理 + PID 类型修复（TDD）。
5. OCR 常驻 worker（TDD）+ 日历按日缓存（TDD）。
6. stage_durations_s 透传。
7. 全量验证。

## 2026-10-24 结果
- pytest 321 passed；64/32 位 compileall 通过。
- 6 个 AutoIPO 任务全部 Ready + WakeToRun=true；推送通道 notify-test 实测成功（pushid 63622712）。
- runtime_data 6 个 `*_test.py` 垃圾脚本删除——它们此前每次 pytest 全量运行都被收集并在模块级向测试文件追加重复用例（测试文件膨胀、登录组合测试反复假失败的根因）。
- pytest.ini 限定 testpaths=tests，防复发。
- 周六真实 GUI 登录验证：THS 主窗顶层用户名 OCR 取不到（券商周末维护，顶栏无用户名）——两个 THS 账户均 THS_CURRENT_ACCOUNT_OCR_FAILED/UNREADABLE，属周末预期，非回归；OCR worker 单机实测 2.8s 正常。
- 遗留：周一 10-27 定时任务真实触发验证（含速度：OCR worker + 弹窗处理 + stage 耗时观测）；中鼎转03（10-22 申购）中签结果因周四/周五检查任务均未触发而漏查，需用户手动在客户端查一次；AutoIPO-CatchUp-Logon 曾有 0xC0000142 一次（待观察）。

## 2026-10-24 下午：真实 GUI 登录验证（修复后）

- **我自己的 bug**：serve-first 补丁后 `proc` 在 worker 成功路径未定义仍被引用 → NameError → THS_CURRENT_ACCOUNT_OCR_FAILED。已修（只判 result.status）+ 回归测试。教训：回退分支变量作用域必须随分支一起走。
- **真实数据**：健康户 13-27s/户（周四 45s，OCR worker+弹窗修复见效）；许*鸣融 26.1s 正常；刘*豪 107.8s 离群待查。
- **周末现象**：5 个平安户（揭*/陈*燕/许*峰/陈*凯/程*宇）not_logged_in 各烧 ~140s（连续中段失败→怀疑限流/会话抖动，周一观察）；华宝 2 户 dialog_closed 快速跳过（23-25s，回退路径工作正常）；中信建投许*鸣融周末可登。
- **fail-fast 仍是最大提速点**：not_logged_in 140s→目标 25s，工作日 15 户若全健康约 6-8min；3min 目标需架构级改动（xiadan 单会话内连续切户免重启），建议先以 5min 为阶段目标。
- 结果行字段是 display_text/target_key（不是 account/display_name）。
