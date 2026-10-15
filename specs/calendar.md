# 打新日历数据源与字段规格

## 数据源

东方财富数据中心统一接口：`GET https://datacenter-web.eastmoney.com/api/data/v1/get`
公共参数：`columns=ALL&pageSize=50&pageNumber=1`，按日过滤 `filter=(<日期字段>='YYYY-MM-DD')`。

| 品种 | reportName | 申购日期字段 |
|---|---|---|
| 新股 | `RPTA_APP_IPOAPPLY` | `APPLY_DATE` |
| 可转债 | `RPT_BOND_CB_LIST` | `PUBLIC_START_DATE` |

响应 `success=false` 或 `result=null` 视为当日无标的（含非交易日），不视为错误。

## 规范化字段（parse 输出）

### 新股（parse_new_stock）
| 输出字段 | 来源字段 | 说明 |
|---|---|---|
| code | SECURITY_CODE | 股票代码 |
| apply_code | APPLY_CODE | 申购代码 |
| name | SECURITY_NAME_ABBR | 简称 |
| market | MARKET_TYPE_NEW | 板块（用于权限过滤） |
| apply_date | APPLY_DATE | 前 10 位 |
| apply_limit | ONLINE_APPLY_UPPER | 申购上限（股） |
| top_marketcap_wan | TOP_APPLY_MARKETCAP | 顶格所需市值（万元） |
| issue_price | ISSUE_PRICE | 发行价，可为 null |
| ballot_pay_date | BALLOT_PAY_DATE | 中签缴款日（M4 用） |

### 可转债（parse_cb）
| 输出字段 | 来源字段 | 说明 |
|---|---|---|
| code | SECURITY_CODE | 债券代码 |
| apply_code | CORRECODE | 申购代码（"XX发债"） |
| name | SECURITY_NAME_ABBR | 简称 |
| rating | RATING | 债项评级 |
| issue_scale_yi | ACTUAL_ISSUE_SCALE | 发行规模（亿） |
| stock_name | SECURITY_SHORT_NAME | 正股简称 |
| apply_date | PUBLIC_START_DATE | 前 10 位 |

## 验收规则

- 已知交易日抽查：2026-10-15 应含「华纬转债(071380)」，2026-10-16 应含「中科转债(371175)」。
- 接口字段变更导致解析失败时，宁可抛错也不静默返回错误数据。
