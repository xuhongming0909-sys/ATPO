# AI-SUMMARY: AutoIPO Windows 计划任务注册——时间唯一来源 config schedule（经 run.py schedule-json），含开机/联网 catch-up
$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$run32 = Join-Path $root 'scheduler\run32.cmd'
$run64 = Join-Path $root 'scheduler\run64.cmd'
$runPy = Join-Path $root 'run.py'
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$settings.WakeToRun = $true  # 睡眠/休眠到点唤醒执行，防止 22:00 中签检查被睡眠吞掉

# 时间唯一来源：config/config.yaml -> python run.py schedule-json（只读 CLI 输出 JSON）
function Invoke-ScheduleJson([string]$Exe, [string[]]$ExeArgs) {
    $out = & $Exe @ExeArgs 2>&1
    if ($LASTEXITCODE -ne 0) { return $null }
    return ($out | Out-String)
}

$scheduleText = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $scheduleText = Invoke-ScheduleJson 'py' @('-3.12', $runPy, 'schedule-json')
}
if (-not $scheduleText) {
    $scheduleText = Invoke-ScheduleJson 'python' @($runPy, 'schedule-json')
}
if (-not $scheduleText) {
    throw '[SCHEDULE_JSON_FAILED] 无法执行 python run.py schedule-json；请确认 Python 可用且 config/config.yaml 有效'
}
try {
    $schedule = $scheduleText | ConvertFrom-Json
} catch {
    throw "[SCHEDULE_JSON_INVALID] schedule-json 输出无法解析为 JSON: $($_.Exception.Message)"
}
foreach ($key in 'calendar_fetch', 'subscribe_time', 'allotment_check_1', 'allotment_check_2') {
    $value = [string]$schedule.$key
    if ($value -notmatch '^([01]\d|2[0-3]):[0-5]\d$') {
        throw "[SCHEDULE_INVALID] schedule.$key=$value 必须是 HH:MM（唯一来源 config/config.yaml）"
    }
}

# 单同花顺切户模式：所有 GUI 任务走 ths-cycle 阶段入口
$bootArgs = 'ths-cycle --phase login'
$subscribeArgs = 'ths-cycle --phase subscribe --live'
$allotmentArgs = 'ths-cycle --phase allotment'

function Register-WeekdayTask([string]$Name, [string]$Program, [string]$Arguments, [string]$Time) {
    try {
        $action = New-ScheduledTaskAction -Execute $Program -Argument $Arguments -WorkingDirectory $root
        $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $Time
        Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    } catch {
        throw "[REGISTER_FAILED] $Name ($Time) 注册失败: $($_.Exception.Message)"
    }
}

# 开机 Logon：先自动登录，再 catch-up 补当日遗漏（catch-up 内部按 TaskStateStore 幂等）
try {
    $bootAction = New-ScheduledTaskAction -Execute $run32 -Argument $bootArgs -WorkingDirectory $root
    $bootTrigger = New-ScheduledTaskTrigger -AtLogOn
    $bootTrigger.Delay = 'PT1M'
    Register-ScheduledTask -TaskName 'AutoIPO-BootLogin' -Action $bootAction -Trigger $bootTrigger -Principal $principal -Settings $settings -Force | Out-Null
} catch {
    throw "[REGISTER_FAILED] AutoIPO-BootLogin 注册失败: $($_.Exception.Message)"
}
try {
    $catchAction = New-ScheduledTaskAction -Execute $run32 -Argument 'catch-up --live' -WorkingDirectory $root
    $catchTrigger = New-ScheduledTaskTrigger -AtLogOn
    $catchTrigger.Delay = 'PT2M'
    Register-ScheduledTask -TaskName 'AutoIPO-CatchUp-Logon' -Action $catchAction -Trigger $catchTrigger -Principal $principal -Settings $settings -Force | Out-Null
} catch {
    throw "[REGISTER_FAILED] AutoIPO-CatchUp-Logon 注册失败: $($_.Exception.Message)"
}

# 网络连接事件 catch-up：NetworkProfile EventID 10000 = 网络配置已启用
try {
    $eventSubscription = "*[System[Provider[@Name='Microsoft-Windows-NetworkProfile'] and (EventID=10000)]]"
    $quotedRun32 = '"' + $run32 + '" catch-up --live'
    & schtasks.exe /Create /TN 'AutoIPO-CatchUp-Network' /TR $quotedRun32 /SC ONEVENT /EC System /MO $eventSubscription /RU $env:USERNAME /IT /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks exit=$LASTEXITCODE"
    }
} catch {
    throw "[REGISTER_FAILED] AutoIPO-CatchUp-Network 注册失败: $($_.Exception.Message)"
}

# 工作日定时任务：时间全部取自 config schedule
Register-WeekdayTask 'AutoIPO-DailyReport' $run64 'daily-report' $schedule.calendar_fetch
Register-WeekdayTask 'AutoIPO-Subscribe' $run32 $subscribeArgs $schedule.subscribe_time
Register-WeekdayTask 'AutoIPO-Allotment-T1' $run32 $allotmentArgs $schedule.allotment_check_1
Register-WeekdayTask 'AutoIPO-Allotment-T2' $run32 $allotmentArgs $schedule.allotment_check_2

Write-Host ("注册完成: DailyReport={0} Subscribe={1} Allotment-T1={2} Allotment-T2={3}" -f $schedule.calendar_fetch, $schedule.subscribe_time, $schedule.allotment_check_1, $schedule.allotment_check_2)
