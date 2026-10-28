# Mission Plan：登录回执动态账户计数与身份识别

## 步骤
1. 更新正式 spec 与 Constitution：普通账户识别信息可显示，凭据仍保护；登录回执以唯一资金账户动态计数。
2. RED：新增 13 唯一账户、重复行、身份字段和错误脱敏边界测试，先确认失败。
3. GREEN：统一 `account_key`，修复 `_ths_phase_items`、`_phase_items`、`_login_counts` 和回执正文。
4. 验证：pytest、compileall 64/32 位、doctor。
5. 真实验收：运行 `python run.py ths-cycle --date 2026-10-18 --phase login`，核对动态总数与实际 session 数。
6. 完整流程验收：`calendar` + `ths-cycle --phase all`（不加 `--live`），确认申购 dry-run、中签查询和推送链路。

## 验证结果
（完成后填写真实命令输出摘要。）

## 结果
（完成后填写。）

## 风险与遗留
（完成后填写。）