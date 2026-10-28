# AI-SUMMARY: 生成可复制项目压缩包——强制排除敏感配置、运行数据和缓存，并在压缩前后验证排除项
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

$ExcludedDirectoryNames = @("runtime_data", ".venv32", "__pycache__", ".pytest_cache", ".git", "screenshots")
$ExcludedFileNames = @("secrets.yaml")
$ImageExtensions = @(".png", ".jpg", ".jpeg", ".bmp", ".gif")

function Resolve-RootPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd([char[]]@(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    ))
}

function Resolve-ProjectChildPath {
    param([string]$Root, [string]$Path)
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Root $Path))
}

function Test-PathInsideWorkspace {
    param([string]$Root, [string]$Path)
    $rootFull = Resolve-RootPath $Root
    $pathFull = [System.IO.Path]::GetFullPath($Path)
    if ($pathFull.Equals($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    $prefix = $rootFull + [System.IO.Path]::DirectorySeparatorChar
    return $pathFull.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Assert-PathInsideWorkspace {
    param([string]$Root, [string]$Path, [string]$Purpose)
    if (-not (Test-PathInsideWorkspace $Root $Path)) {
        throw "[PACKAGE_PATH_OUTSIDE_WORKSPACE] $Purpose must stay inside $Root : $Path"
    }
}

function Get-RelativePath {
    param([string]$Root, [string]$Path)
    $rootFull = Resolve-RootPath $Root
    $pathFull = [System.IO.Path]::GetFullPath($Path)
    return $pathFull.Substring($rootFull.Length).TrimStart([char[]]@(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    ))
}

function Test-ExcludedRelativePath {
    param([string]$RelativePath)
    $normalized = $RelativePath.Replace("\", "/").TrimStart("/")
    $segments = @($normalized -split "/")
    foreach ($segment in $segments) {
        if ($ExcludedDirectoryNames -contains $segment) {
            return $true
        }
    }
    if ($ExcludedFileNames -contains $segments[-1]) {
        return $true
    }
    if ($normalized -ieq "config/secrets.yaml") {
        return $true
    }
    $extension = [System.IO.Path]::GetExtension($segments[-1]).ToLowerInvariant()
    if (($ImageExtensions -contains $extension) -and ($segments[-1] -match "(?i)screenshot|截图")) {
        return $true
    }
    return $false
}

function Remove-WorkspacePath {
    param([string]$Root, [string]$Path, [string]$Purpose)
    if (Test-Path -LiteralPath $Path) {
        Assert-PathInsideWorkspace $Root $Path $Purpose
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Resolve-RootPath (Join-Path $PSScriptRoot "..")
} else {
    $ProjectRoot = Resolve-RootPath $ProjectRoot
}
if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    throw "[PACKAGE_ROOT_MISSING] Project root not found: $ProjectRoot"
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $ProjectRoot "runtime_data/package/auto-ipo-clean.zip"
} else {
    $OutputPath = Resolve-ProjectChildPath $ProjectRoot $OutputPath
}
Assert-PathInsideWorkspace $ProjectRoot $OutputPath "output path"

$packageDir = Split-Path -Parent $OutputPath
$stage = Join-Path $packageDir (".package-stage-" + [System.Guid]::NewGuid().ToString("N"))
$zipTemp = Join-Path $packageDir (".package-zip-" + [System.Guid]::NewGuid().ToString("N") + ".zip")
foreach ($path in @($packageDir, $stage, $zipTemp)) {
    Assert-PathInsideWorkspace $ProjectRoot $path "package workspace path"
}

$outputCreated = $false
try {
    New-Item -ItemType Directory -Path $packageDir -Force | Out-Null
    New-Item -ItemType Directory -Path $stage -Force | Out-Null

    $pending = New-Object "System.Collections.Generic.Queue[string]"
    $pending.Enqueue($ProjectRoot)
    while ($pending.Count -gt 0) {
        $current = $pending.Dequeue()
        foreach ($item in @(Get-ChildItem -LiteralPath $current -Force)) {
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                continue
            }
            $relative = Get-RelativePath $ProjectRoot $item.FullName
            if (Test-ExcludedRelativePath $relative) {
                continue
            }
            $destination = Join-Path $stage $relative
            if ($item.PSIsContainer) {
                New-Item -ItemType Directory -Path $destination -Force | Out-Null
                $pending.Enqueue($item.FullName)
            } else {
                Copy-Item -LiteralPath $item.FullName -Destination $destination -Force
            }
        }
    }

    foreach ($item in @(Get-ChildItem -LiteralPath $stage -Recurse -Force)) {
        $relative = Get-RelativePath $stage $item.FullName
        if (Test-ExcludedRelativePath $relative) {
            throw "[PACKAGE_FORBIDDEN_ARTIFACT] forbidden item reached staging: $relative"
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $stage "config/secrets.example.yaml") -PathType Leaf)) {
        throw "[PACKAGE_TEMPLATE_MISSING] config/secrets.example.yaml is required in the clean package"
    }

    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $stage,
        $zipTemp,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $false
    )
    Assert-PathInsideWorkspace $ProjectRoot $zipTemp "temporary zip"
    Remove-WorkspacePath $ProjectRoot $OutputPath "existing output"
    Move-Item -LiteralPath $zipTemp -Destination $OutputPath
    Assert-PathInsideWorkspace $ProjectRoot $OutputPath "final output"
    $outputCreated = $true

    $archive = [System.IO.Compression.ZipFile]::OpenRead($OutputPath)
    try {
        foreach ($entry in $archive.Entries) {
            if (Test-ExcludedRelativePath $entry.FullName) {
                throw "[PACKAGE_FORBIDDEN_ARTIFACT] forbidden item reached zip: $($entry.FullName)"
            }
        }
        $entryCount = $archive.Entries.Count
    } finally {
        $archive.Dispose()
    }

    [pscustomobject]@{
        ok = $true
        output = $OutputPath
        entry_count = $entryCount
        bytes = (Get-Item -LiteralPath $OutputPath).Length
        excluded = $ExcludedDirectoryNames + $ExcludedFileNames
        verified = $true
    } | ConvertTo-Json -Compress
} catch {
    Remove-WorkspacePath $ProjectRoot $zipTemp "failed temporary zip"
    if ($outputCreated) {
        Remove-WorkspacePath $ProjectRoot $OutputPath "failed output"
    }
    throw
} finally {
    Remove-WorkspacePath $ProjectRoot $stage "package staging directory"
}