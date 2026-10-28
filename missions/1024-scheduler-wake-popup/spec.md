# 1024 计划任务触发修复与一键打新弹窗

## 任务类型
修复 + 增强。

## 目标
1. 计划任务到点必须触发（周五 10-23 全天零运行、周四晚中签检查未推送）。
2. 登录后「一键打新」弹窗不再阻塞/卡慢流程。

## 范围
- scheduler/register_tasks.ps1：WakeToRun、尾部语法错误修复、重新注册。
- execution/login.py：一键打新弹窗识别（勾「不再自动弹出」后关窗）；PID 比较 str/int 类型不匹配修复（_dismiss_popups/close_modal_dialogs 等 4 处）。
- shared/username_ocr.py：常驻 64 位 OCR worker（--serve JSON 行协议），消除每次冷启动。
- data_fetch/calendar.py：进程内按日缓存。
- execution/ths_account_runner.py：stage_durations_s 透传到结果行。
- 电源：唤醒定时器 AC/DC 启用；TaskScheduler 诊断日志启用。
- 测试基建：pytest.ini（testpaths=tests），删除 runtime_data 下被 pytest 当测试收集的垃圾脚本。

## 约束
- 弹窗处理绝不点申购/确定类按钮（不变量 §6-6 精神）。
- 一键打新弹窗永不作为申购入口（申购只走批量页）。
- 敏感凭据规则不变。

## 对正式 spec 的影响
- specs/operations.md 计划任务节：任务须 WakeToRun + 唤醒定时器。
- 逻辑图.MD §7 快照更新。
