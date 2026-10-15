# Claude Code PreToolUse hook used by Zyraena's sleep mode (sleep_mode.py).
#
# Runs before every tool call that can change files. It works out which project folders
# under the sleep-mode roots (Documents\Projects, Documents\Work) the call may touch, and
# copies each one into the night's Failsafe folder the first time, before anything in it
# changes. If a copy fails, the call is blocked (exit 2): nothing changes without a backup.
param(
    [Parameter(Mandatory)][string]$Failsafe,
    [Parameter(Mandatory)][string]$Roots,  # separated by ;
    [string]$Forbidden = ''  # folders that must never change (e.g. the Telegram bridge), separated by ;
)
$ErrorActionPreference = 'Stop'
$skip = @('.venv', 'venv', 'node_modules', '__pycache__')

$call = [Console]::In.ReadToEnd() | ConvertFrom-Json
$input_ = $call.tool_input
$candidates = New-Object System.Collections.Generic.List[string]
foreach ($key in 'file_path', 'notebook_path', 'path') {
    if ($input_.$key) { $candidates.Add([string]$input_.$key) }
}
$rootList = $Roots.Split(';') | Where-Object { $_ } | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') }
if ($call.tool_name -in 'Bash', 'PowerShell') {
    # A command may change files anywhere: back up the folder it runs in and every project
    # folder its text names.
    if ($call.cwd) { $candidates.Add([string]$call.cwd) }
    $text = [string]$input_.command
    foreach ($root in $rootList) {
        $pattern = [regex]::Escape($root).Replace('\\', '[\\/]+') + '[\\/]+([^\\/"''\r\n]+)'
        foreach ($m in [regex]::Matches($text, $pattern, 'IgnoreCase')) {
            $candidates.Add((Join-Path $root $m.Groups[1].Value.Trim()))
        }
    }
}

$forbiddenList = $Forbidden.Split(';') | Where-Object { $_ } | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') }
if ($call.tool_name -in 'Bash', 'PowerShell') {
    foreach ($folder in $forbiddenList) {
        if ($text.IndexOf((Split-Path $folder -Leaf), [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $candidates.Add($folder)
        }
    }
}

$problems = @()
foreach ($candidate in $candidates) {
    try { $full = [IO.Path]::GetFullPath(($candidate -replace '/', '\')) } catch { continue }
    foreach ($folder in $forbiddenList) {
        if ($full -eq $folder -or $full.StartsWith($folder + '\', [StringComparison]::OrdinalIgnoreCase)) {
            [Console]::Error.WriteLine("Sleep mode: $folder is off-limits (it holds Zyraena's Telegram " +
                "bridge and its secrets). Leave it alone and find another way.")
            exit 2
        }
    }
    foreach ($root in $rootList) {
        if (-not $full.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { continue }
        $top = $full.Substring($root.Length + 1).Split('\')[0]
        if (-not $top) { continue }
        $source = Join-Path $root $top
        $target = Join-Path $Failsafe ((Split-Path $root -Leaf) + '_' + $top)
        if (Test-Path -LiteralPath $target) { continue }  # backed up earlier tonight
        if (Test-Path -LiteralPath $source -PathType Container) {
            & robocopy $source $target /E /XD @skip /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
            if ($LASTEXITCODE -ge 8) {
                Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
                $problems += "$source (robocopy exit code $LASTEXITCODE)"
            } else {
                Add-Content -LiteralPath (Join-Path $Failsafe 'backed_up.txt') -Value "$source|$target" -Encoding UTF8
            }
        } elseif (Test-Path -LiteralPath $source -PathType Leaf) {
            New-Item -ItemType Directory -Path $target -Force | Out-Null
            Copy-Item -LiteralPath $source -Destination $target
            Add-Content -LiteralPath (Join-Path $Failsafe 'backed_up.txt') -Value "$source|$target" -Encoding UTF8
        }
        # A folder that doesn't exist yet is being created: there's nothing to back up.
    }
}

if ($problems) {
    [Console]::Error.WriteLine("Sleep mode: the Failsafe backup failed for: $($problems -join ', '). " +
        "Don't change these files; try another way or leave this part out and explain it in the report.")
    exit 2
}
exit 0
