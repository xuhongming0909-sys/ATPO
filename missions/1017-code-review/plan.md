# Mission Plan

## 步骤
1. 按 Read Order 读取 AGENTS.md、INDEX.md、README.md、specs/*.md、config/config.yaml、MEMORY.md。
   验证：治理规则、正式需求、账户/调度/安全约束均已核对。
2. 盘点工作树、源码规模、测试、运行时数据和 Windows 计划任务。
   验证：5 个 AutoIPO 任务可查询；源码最大 598 行，未超过 1000 行。
3. 运行无副作用的 compileall、CLI help、doctor、64 位 pytest 和 32 位依赖导入检查。
   验证：compileall=0；help=0；doctor ok=true；当前快照 pytest 91 passed；32 位执行依赖可导入。
4. code-reviewer、clean-code-reviewer、debugger 三个视角并行审查。
   验证：实盘正确性、代码质量、端到端故障链 findings 均带绝对路径和行号。
5. 本地交叉核对高风险 findings，合并去重并分级。
   验证：P0 批量申购范围失控、P0 台账损坏 fail-open 均有静态代码证据；debugger 另有安全桩复现。

## 验证结果
- `python -m pytest -q`：当前快照 91 passed。审查期间 13:57-14:04 有并发代码写入；早期并行验证出现 1 个瞬时失败，隔离与随后全量重跑通过。
- `python -m compileall -q run.py data_fetch execution notification scheduler shared webui tests`：exit 0。
- `python run.py --help`：exit 0。
- `python run.py doctor`：ok=true，errors=[]；配置、DPAPI、两个客户端路径和模板检查通过。
- 32 位 Python 3.11.9：jqktrader、pywinauto、win32gui、cv2、numpy、pandas、yaml、requests 可导入；`.venv32` 未安装 pytest。
- `schtasks`：5 个任务均存在且 Ready；BootLogin 当前 Last Result=1，且尚无当前实现下完整日志/台账证据。
- 未触发真实登录、申购、下单或推送。

## 结果
审查完成。当前数据抓取、调度、通知主链完整，但 live 链存在两个 P0：批量页未受当日日历/permissions/blacklist allowlist 约束；订单台账损坏时 fail-open。修复前不应把 live 重跑视为安全。

## 风险与遗留
- 工作树有大量未提交实现；本审查覆盖当前工作树，不等同已提交 release。
- GUI 控件、真实券商回执、节假日/交易日、通知去重仍需真实交易日回归；审查期间检测到并发代码变更，后续修复需先锁定工作树。
- 需优先修复：批量 allowlist、台账 fail-closed、账户唯一识别/资金账号控件绑定、SendKey 脱敏、双客户端隔离和增量审计落盘；`shared/gui_lock.py` 当前锁字节位置随文件末尾漂移，已实测两个句柄可同时加锁。