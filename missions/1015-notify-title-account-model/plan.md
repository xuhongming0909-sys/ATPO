# Mission 1015-notify-title-account-model — Plan

## 步骤
1. 改 tests/test_report.py：标题含日期/只数/名称、超阈值折叠（RED）
2. 改 scheduler/jobs.py：_make_title 实现（GREEN）
3. 实推验证新标题
4. config.yaml 账户模型扩展 note/account_type/bj_enabled
5. 同步 specs（requirements v3.1 / notification 标题规则 / calendar 市场覆盖）
6. 更新 MEMORY 收尾

## 验证结果
- `pytest` → 6 passed（含新增标题折叠测试）
- `run.py daily-report --day 2026-10-16` 实推标题：`10-16 打新 1 只：中科转债(债)`，微信送达
- 东财 MARKET_TYPE_NEW 实测取值：上交所其他/深交所其他/创业板注册制/科创板/北交所

## 结果
完成。

## 风险与遗留
- jqktrader/easytrader 通用同花顺模式要求客户端处于已登录状态（首次需用户手动登录一次并勾选记住密码），之后程序接管；验证码场景 M2 实测确认（备 Tesseract OCR）。
- M3 管理界面技术选型未定（倾向本地 Web 表单）。
- 2026-10-15 追加：日历推送改为当日+明日双日、标题带顶格数量、打新执行时间定 10:00，均已实现并实推验证；同花顺 xiadan.exe 确认安装正常（2026.07.02），「无法正常使用」现象待用户说明。
- 可转债顶格展示暂定「1 万张」，M2 实盘以客户端实际顶格校验。
