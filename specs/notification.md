# 通知规格

## 1. 通道

| 通道 | 用途 | 配置位置 |
|---|---|---|
| Server酱 Turbo（主） | 全部消息 | `config/secrets.yaml → serverchan.sendkey` |
| 邮件（预留） | 中签缴款等关键消息兜底（M4） | — |

## 2. 消息类型

| 类型 | 触发 | 内容要点 |
|---|---|---|
| 打新日历 | 每交易日 08:25（Windows 任务计划） | **一条推送**含当日+明日，标题分段 `10/15 华纬转债 1万张；10/16 中科转债 1万张`，正文分「今日」「明日」两节 |
| 登录回执 | 登录任务结束后 | 已登录/需人工/失败数量，按 THS 账户和资金账户列出完整操作明细 |
| 申购回执（M2） | 每日 10:00 申购执行后 | 标的、证券代码、账户、数量、状态、失败原因和下一步 |
| 中签回执（M4） | T+1 晚 22:00 / T+2 早 08:00 | 账户、标的、中签数量、缴款金额和缴款提醒 |

## 3. 回执公开契约

模块：`notification/receipts.py`

```python
render_receipt(kind: str, data: Mapping[str, Any]) -> tuple[str, str]
send_receipt(kind: str, data: Mapping[str, Any]) -> dict
```

- `kind` 仅允许 `login`、`subscribe`、`allotment`，其他值抛 `ValueError`。
- `data` 固定支持 `date`、`summary`、`clients`、`items`、`next_action`；登录明细还必须携带 `account_key`、`ths_account`、`display_name`、`fund_account_tail4` 等身份字段。
- `render_receipt` 是纯函数：不读取配置、不联网、不写日志；同输入始终得到同标题和正文。
- 固定字段顺序为：日期、结果、客户端/标的明细、提醒、下一步，便于日志检索。
- `send_receipt` 按 `notification_receipts.send_login/send_subscribe/send_allotment` 决定是否调用 `notification.serverchan.send`。
- 开关关闭返回 `{"kind": ..., "sent": false, "reason": "disabled"}`，不得联网。
- 模板版本由 `notification_receipts.template_version` 管理，当前正式模板版本为 `2`。

### 3.1 登录回执

账户总数按唯一资金账户动态计算，不能按 THS 行数、重复行数或固定值计算。成功仅包含 `ready`、`already_logged_in`；其他状态统一计为失败，失败原因在正文说明。

标题格式：

```text
[登录回执][M/D] 账户 X｜成功 X｜失败 X
```

正文格式：

```text
日期：YYYY-MM-DD
账户总数：X
成功：X
失败：X
[THS: mx_525378109] 账户 X｜成功 X｜失败 X
1. 账户：平安证券-张*龙｜资金账号：326219242115｜THS：mx_525378109｜事件：登录成功｜状态码：ready
2. 账户：中信建投证券-许*鸣融｜THS：mx_525378109｜结果：失败｜状态：dialog_closed｜原因：资金账户登录弹窗已关闭
下一步：...
```

### 3.2 申购回执

标题格式：

```text
[申购回执][M/D] 成功 X｜跳过 X｜失败 X
```

正文每条固定包含：

```text
- 账户：账户名｜标的：名称（证券代码）｜数量：N 单位｜状态：status｜失败原因：...
```

### 3.3 中签回执

有中签：

```text
[中签回执][M/D] 中签 X 户
```

无中签，标题必须精确为：

```text
[中签回执][M/D] 无中签
```

正文每条固定包含账户名、标的、证券代码、中签数量、缴款金额、状态；有中签时附缴款提醒。数据未公布时正文含“数据未公布，将继续补查”，不得当成最终无中签。

## 4. 信息显示与错误

- THS 用户名、账户显示名、券商名、完整资金账号/尾号、状态、错误码、错误原因、证券代码、数量、时间、截图路径等普通操作信息不做脱敏，直接用于定位具体账户。
- `password`、密码、`captcha`、验证码、SendKey、token、DPAPI 密文等凭据字段递归删除或替换。
- Server酱请求、HTTP、接口、解析异常统一转换为清晰错误；不得包含 SendKey、密码、验证码、token，也不得通过异常链泄露原始 URL。
- 推送失败继续抛出，由调用方决定补发或告警，不静默吞错。

## 5. 执行模块集成

- `execution/subscribe.py` 只负责把执行结果转换为 `subscribe` 数据并调用 `send_receipt`。
- `execution/allotment.py` 只负责把查询结果转换为 `allotment` 数据并调用 `send_receipt`。
- 下单、查询、账户切换和台账逻辑不依赖通知模块；通知失败不得改变已产生的业务结果。
- 打新日历推送继续使用 `scheduler/jobs.py`，不在本回执契约范围内。

