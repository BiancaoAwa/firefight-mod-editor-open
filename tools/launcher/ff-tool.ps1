<#
ff-tool.ps1 - one-click start / stop for the Firefight mod editor tool (the `core.cli` package).

  start    preflight + version + scope overview, then leave a shell where `ff` works
  stop     end leftover editor processes and clean the generated output
  restart  stop, then start
  status   show the paths, what exists, and what is still running
  run      pass the rest of the command line straight to the CLI (this is what `ff` does)
  web      serve the web UI on 127.0.0.1 (-Port <n> pins a port; without it the action reuses
           the instance this editor already records, else takes the first free port from 8765)
           -Window serves it hidden with the page in its own app window and a watchdog;
           -Scope <name> picks the scope (default Firefight, -Project implies Mod);
           -NoBrowser opens no page, -Browser uses the default browser instead of the app window

Every CLI call is appended to <workdir>\tool-<date>.log.
Override paths with -Python/-Cli/-Root/-Project/-WorkDir or the FF_PYTHON / FF_CLI /
FF_ROOT / FF_PROJECT / FF_SCOPE / FF_WORK environment variables.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'restart', 'status', 'run', 'web', 'watch', 'help')]
    [string]$Action = 'start',

    [string]$Python = $env:FF_PYTHON,
    [string]$Cli = $env:FF_CLI,
    [string]$Root = $env:FF_ROOT,
    [string]$Project = $env:FF_PROJECT,
    [string]$WorkDir = $env:FF_WORK,
    [string]$Scope = $env:FF_SCOPE,
    [int]$Port = 0,

    [switch]$Quick,
    [switch]$KeepOutput,
    [switch]$Window,
    [switch]$NoBrowser,
    [switch]$Browser,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$script:Self = $PSCommandPath

$editorParent = Split-Path $PSScriptRoot -Parent
# The DSH-bundled interpreter is a machine fact, not a repository constant: DSH_HOME names the
# installation directory, so no user name and no drive letter is written into this file.
$bundledPython = if ($env:DSH_HOME) {
    Join-Path $env:DSH_HOME 'dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
}
$defaultPython = if ($bundledPython -and (Test-Path -LiteralPath $bundledPython)) { $bundledPython } else { 'python' }
# The launcher ships in two layouts, so the entry point is resolved instead of hard-coded:
#   repository: tools\launcher\ff-tool.ps1     +  ..\..\core\cli\__main__.py
#   release   : <editor>\launcher\ff-tool.ps1  +  ..\core\cli\__main__.py
$cliCandidates = @(
    (Join-Path $editorParent 'core\cli\__main__.py'),
    (Join-Path $editorParent '..\core\cli\__main__.py')
)
$defaultCli = $cliCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $defaultCli) { $defaultCli = $cliCandidates[0] }
$editorRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $defaultCli))
$bundledRoot = Join-Path $editorRoot 'Firefight'
# Logs live next to the core folder, in both layouts (repository and release).
$defaultWork = Join-Path $editorRoot 'Logs'

if (-not $Python) { $Python = $defaultPython }
if (-not $Cli) { $Cli = $defaultCli }
if (-not $WorkDir) { $WorkDir = $defaultWork }

function Get-ConfiguredFirefightRoot {
    # Reads `firefight = "<path>"` from CONFIG_NAME, the key core/cli/scope.py resolves.
    foreach ($dir in @($WorkDir, (Split-Path -Parent $WorkDir), $editorRoot)) {
        if (-not $dir) { continue }
        $configPath = Join-Path $dir 'Setting.toml'
        $text = Get-Content -LiteralPath $configPath -Raw -ErrorAction SilentlyContinue
        if ($text -and $text -match '(?m)^\s*firefight\s*=\s*"([^"]+)"') {
            return ($Matches[1] -replace '/', '\')
        }
    }
    return $null
}

function Get-SteamFirefightRoot {
    # The game directory is a machine fact: probe the standard Steam library roots on every fixed
    # drive rather than naming one drive.
    $relative = @(
        'Program Files (x86)\Steam\steamapps\common\Firefight',
        'Program Files\Steam\steamapps\common\Firefight',
        'Steam\steamapps\common\Firefight',
        'SteamLibrary\steamapps\common\Firefight'
    )
    foreach ($drive in (Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue)) {
        foreach ($part in $relative) {
            $candidate = Join-Path $drive.Root $part
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    }
    return $null
}

$configuredRoot = Get-ConfiguredFirefightRoot
if (-not $Root) {
    $steamRoot = Get-SteamFirefightRoot
    $Root = if ($configuredRoot -and (Test-Path -LiteralPath $configuredRoot)) { $configuredRoot }
        elseif (Test-Path -LiteralPath $bundledRoot) { $bundledRoot }
        elseif ($steamRoot) { $steamRoot }
        else { $bundledRoot }
}
# $Port stays 0 when the caller named none: the web actions then reuse the instance this editor
# already records, else take the first free port at or above $script:DefaultPort.
if ($Port -le 0 -and $env:FF_PORT) { $Port = [int]$env:FF_PORT }
$script:DefaultPort = 8765

$script:LogFile = $null
$script:OutDir = Join-Path $WorkDir 'out'
$script:StateFile = Join-Path $WorkDir 'state.json'
$script:WebStateFile = Join-Path $WorkDir 'web.json'

function Write-Head([string]$Text) {
    Write-Host ''
    Write-Host "== $Text" -ForegroundColor Cyan
}

function Write-Ok([string]$Text) { Write-Host "  [ok]   $Text" -ForegroundColor Green }
function Write-Bad([string]$Text) { Write-Host "  [FAIL] $Text" -ForegroundColor Red }
function Write-Info([string]$Text) { Write-Host "  $Text" -ForegroundColor Gray }

function Initialize-Log {
    if (-not (Test-Path $WorkDir)) { New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null }
    $logDir = $WorkDir
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    $script:LogFile = Join-Path $logDir ('tool-' + (Get-Date -Format 'yyyyMMdd') + '.log')
    Add-Content -Path $script:LogFile -Value ("--- {0} :: {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), ($Action)) -Encoding UTF8
}

function Write-Log([string]$Text) {
    if ($script:LogFile) { Add-Content -Path $script:LogFile -Value $Text -Encoding UTF8 }
}

function Get-CliArgv([string[]]$Arguments) {
    # `-m core.cli` only resolves with the editor root on sys.path, so callers set that cwd.
    return @('-m', 'core.cli') + $Arguments
}

function Get-FfPython {
    # every python process that is running our editor CLI (`python -m core.cli`)
    $pattern = '-m\s+core\.cli'
    Get-CimInstance -ClassName Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $pattern }
}

function Get-FfWeb {
    # python processes that are serving the web ui
    Get-FfPython | Where-Object { $_.CommandLine -and $_.CommandLine -match '\sweb(\s|$)' }
}

function Get-PortOwner([int]$PortNumber) {
    # the pid LISTENING on a port, straight from netstat; 0 when nothing listens
    $line = netstat -ano | Where-Object { $_ -match (":{0}\s" -f $PortNumber) -and $_ -match 'LISTENING' } | Select-Object -First 1
    if (-not $line) { return 0 }
    $parts = ($line.Trim() -split '\s+')
    return [int]$parts[-1]
}

function Test-PortOpen([int]$PortNumber) {
    # a short TCP probe, so `web -Window` can tell whether the server came up
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect('127.0.0.1', $PortNumber, $null, $null)
        $done = $async.AsyncWaitHandle.WaitOne(400)
        $ok = ($done -and $client.Connected)
        $client.Close()
        return $ok
    }
    catch { return $false }
}

function Find-AppBrowser {
    # Output: the path of Edge or Chrome, or '' when neither is installed; the caller then
    # falls back to the default browser. An --app window has no tabs and no address bar.
    foreach ($candidate in @(
            (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'),
            (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
            (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
            (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
            (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
        )) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    return ''
}

function Test-Placeholder([string[]]$Call) {
    # a placeholder pasted from the help text would otherwise be taken as a path
    foreach ($arg in $Call) {
        if ($arg -match '^([A-Za-z_]+)=<(.*)>$') {
            Write-Bad ("{0}=<{1}> is a placeholder, not a path - either drop it and let the tool fill it in, or give a real directory" -f $matches[1], $matches[2])
            return $false
        }
    }
    return $true
}

function Invoke-Ff([string[]]$FfArgs, [switch]$Quiet) {
    $call = @($FfArgs)

    if (-not (Test-Placeholder $call)) { return 2 }
    # Firefight always needs root=, and Mod needs a project: fill in the known value unless
    # the caller passed one, exactly like the plugin does for its Firefight scope.
    $scope = if ($call.Count -gt 0) { $call[0] } else { '' }
    $hasRoot = @($call | Where-Object { $_ -like 'root=*' }).Count -gt 0
    if (-not $hasRoot) {
        if ($scope -eq 'Firefight' -and $Root) { $call += ('root=' + $Root); Write-Info "added   root=$Root" }
        elseif ($scope -eq 'Mod' -and $Project) { $call += ('root=' + $Project); Write-Info "added   root=$Project" }
    }

    $argv = Get-CliArgv $call
    Write-Log ("argv: " + ($argv -join ' '))
    Push-Location $editorRoot
    try { $lines = & $Python @argv 2>&1; $code = $LASTEXITCODE } finally { Pop-Location }
    $text = ($lines | Out-String).TrimEnd()
    if ($text) { Write-Log $text }
    Write-Log "exit=$code"
    if (-not $Quiet) {
        if ($text) { Write-Host $text }
        $colour = if ($code -eq 0) { 'DarkGray' } else { 'Yellow' }
        Write-Host ("  (exit $code)" + $(if ($code -eq 1) { ' - executed failure; the JSON payload is usually still valid' } else { '' })) -ForegroundColor $colour
    }
    return $code
}

function Show-Preflight {
    Write-Head 'preflight'
    $fails = 0

    if (Test-Path $Python) { Write-Ok "python   $Python" } else { Write-Bad "python not found: $Python"; $fails++ }
    if (Test-Path $Cli) { Write-Ok "cli      $Cli" } else { Write-Bad "cli not found: $Cli"; $fails++ }
    if (Test-Path $Root) {
        if (Test-Path (Join-Path $Root 'Data')) { Write-Ok "stock    $Root" }
        else { Write-Bad "stock root has no Data\ directory: $Root"; $fails++ }
    }
    else { Write-Bad "stock root not found: $Root"; $fails++ }

    if ($Project) {
        $manifest = Join-Path $Project 'ModInformation.toml'
        if (Test-Path $manifest) { Write-Ok "project  $Project" }
        else { Write-Bad "no ModInformation.toml in the project directory: $Project"; $fails++ }
    }
    else {
        Write-Info 'project  (none) - Mod scope needs -Project <dir with ModInformation.toml> or root=<dir>'
    }
    return $fails
}

function Start-Tool {
    $fails = Show-Preflight

    Write-Head 'editor'
    Invoke-Ff @('version', "root=$Root")

    if (-not $Quick) {
        Write-Head 'stock data'
        Push-Location $editorRoot
        try { $json = & $Python @(Get-CliArgv @('Firefight', 'stats', "root=$Root", '--json')) 2>&1; $code = $LASTEXITCODE } finally { Pop-Location }
        Write-Log ("argv: Firefight stats root=$Root --json")
        if ($code -eq 0 -or $code -eq 1) {
            $text = ($json | Out-String)
            Write-Log $text
            try {
                $s = $text | ConvertFrom-Json
                Write-Ok ("Firefight: {0} files, {1} bytes, {2} lists" -f $s.files, $s.bytes, $s.lists)
                $cats = @()
                foreach ($p in $s.by_category.PSObject.Properties) { $cats += ("{0} {1}" -f $p.Name, $p.Value) }
                Write-Info ("  " + ($cats -join ', '))
            }
            catch { Write-Bad 'stats output was not JSON' }
        }
        else { Write-Bad "stats exited with $code" }
    }

    $state = [ordered]@{
        startedAt = (Get-Date).ToString('s')
        pid = $PID
        python = $Python
        cli = $Cli
        root = $Root
        project = $Project
        workDir = $WorkDir
        log = $script:LogFile
    }
    ($state | ConvertTo-Json) | Set-Content -Path $script:StateFile -Encoding UTF8

    # leave a shell alias so the same window can drive the CLI directly
    $sb = [scriptblock]::Create("& '$($script:Self)' run @args")
    Set-Item -Path 'function:global:ff' -Value $sb -Force

    # the in-shell verbs (status, stop, ...) are registered after the switch, in the script's
    # own scope: a function scope cannot take over the global read-only `start` alias.
    $script:BlockedVerbs = @()
    Set-Item -Path 'function:global:ff-help' -Value ([scriptblock]::Create("& '$($script:Self)' help @args")) -Force

    Write-Head 'ready'
    Write-Ok "state    $script:StateFile"
    Write-Ok "log      $script:LogFile"
    Write-Info 'the CLI is also available as:  ff <scope> <command> [selector] [key=value ...] [--json]'
    Write-Info 'for the Firefight scope the tool adds root= by itself, so these work as typed:'
    Write-Info '  ff Firefight stats --json'
    Write-Info '  ff Firefight show Data/Weapons/WEAPON_PISTOL_P38.txt as=toml --json'
    Write-Info '  ff Firefight deps value=WEAPON_PISTOL_P38 --json'
    Write-Info '  ff Firefight check --json'
    Write-Info ("the stock root is:  " + $Root)
    Write-Info 'to query another project, pass root=<that directory> (a real path, not a placeholder)'
    Write-Info 'a `Mod` scope needs -Project <dir with ModInformation.toml> when the window starts'
    Write-Info 'stop the tool with:  stop'
    Write-Info ("open the pages in their own window:  web-open   (port {0})" -f $(if ($Port -gt 0) { $Port } else { "auto" }))
    Write-Info 'web-open starts the UI hidden and leaves this prompt free (nothing to close but the page)'
    Write-Info 'in-shell shortcuts: status | stop | restart | ff-start | web | web-open | ff <CLI args> | ff-help'
    Write-Info '  (`start` is PowerShell''s own Start-Process alias, so start is typed ff-start)'
    Write-Info 'close this window with:  exit'
    if ($fails -gt 0) { Write-Bad "$fails preflight problem(s) - fix them before testing" }
    return $fails
}

function Get-WebScope {
    # Output: the scope name to serve. Precedence: -Project, -Scope, then Firefight. A named
    # scope is resolved by the CLI itself, so root= is added only for -Project and for the
    # Firefight scope (see Get-WebRootArgs).
    if ($Project) { return 'Mod' }
    if ($Scope) { return $Scope }
    return 'Firefight'
}

function Get-WebRootArgs([string]$Name) {
    if ($Project) { return @('root=' + $Project) }
    if ($Name -eq 'Firefight') { return @('root=' + $Root) }
    return @()
}

function Get-WebRootText([string]$Name) {
    $args = @(Get-WebRootArgs $Name)
    if ($args.Count -gt 0) { return $args[0].Substring(5) }
    return '(resolved by the editor config)'
}

function Start-Web {
    # the server runs in the foreground and streams its banner, so this does not go through
    # Invoke-Ff (which buffers the child's output until it exits)
    $scope = Get-WebScope
    # no port named: the CLI reuses the recorded instance or takes the first free port itself
    $portArgs = if ($Port -gt 0) { @('port=' + $Port) } else { @() }
    $call = @($scope, 'web') + @(Get-WebRootArgs $scope) + $portArgs + @($Rest)
    # in the foreground there is no launcher left to open a window, so the CLI opens the
    # default browser itself; -NoBrowser (or an inherited FF_WEB_BROWSER=0) suppresses that
    if ((-not $NoBrowser) -and ($env:FF_WEB_BROWSER -ne '0')) { $call += 'browser=1' }
    if (-not (Test-Placeholder $call)) { return 2 }

    Write-Head 'web ui'
    Write-Info ("python   " + $Python)
    Write-Info ("cli      python -m core.cli  (" + $Cli + ")")
    Write-Info ("scope    " + $scope)
    Write-Info ("root     " + (Get-WebRootText $scope))
    if ($Port -gt 0) {
        Write-Info ("url      http://127.0.0.1:{0}/" -f $Port)
    } else {
        # no port named: the CLI takes the first free port and prints the address it bound
        Write-Info ("url      the first free port at or above {0}; the server prints the address" -f $script:DefaultPort)
    }
    Write-Info 'this window stays busy while the server runs - press Ctrl-C to stop it'
    Write-Info 'the server is read-only and only binds 127.0.0.1'
    $argv = Get-CliArgv $call
    Write-Log ("argv: " + ($argv -join ' '))
    Push-Location $editorRoot
    try { & $Python @argv } finally { Pop-Location }
    $code = $LASTEXITCODE
    Write-Log "exit=$code"
    Write-Head 'web ui stopped'
    if ($code -eq 0) { Write-Ok ("server stopped (exit {0})" -f $code) }
    elseif ($Port -gt 0) { Write-Bad ("server exited with {0} - is port {1} already in use?" -f $code, $Port) }
    else { Write-Bad ("server exited with {0}" -f $code) }
    Write-Info 'start it again with:  web'
    return $code
}

function Get-WebInstanceFile {
    # the record the CLI writes for the instance it serves (core/web/server.py)
    Join-Path $editorRoot 'EditorCache\web.json'
}

function Read-WebInstance {
    # the recorded instance when its address still answers, else $null; the file is written by
    # this editor only, so a port answered by another program is never taken for ours
    $file = Get-WebInstanceFile
    if (-not (Test-Path $file)) { return $null }
    try { $record = Get-Content $file -Raw | ConvertFrom-Json } catch { return $null }
    if (-not $record.url) { return $null }
    if ($record.url -match ':(\d+)/' -and (Test-PortOpen ([int]$Matches[1]))) { return $record }
    return $null
}

function Find-FreePort([int]$Start) {
    # first port at or above $Start nothing answers on; the CLI resolves the same way
    for ($p = $Start; $p -lt ($Start + 50); $p++) { if (-not (Test-PortOpen $p)) { return $p } }
    return $Start
}

function Open-ReusedPage([string]$Url) {
    # no watchdog here: the server belongs to whoever started it, not to this window
    if ($NoBrowser) { Write-Info 'page     not opened (-NoBrowser) - the address is above'; return }
    $exe = if ($Browser) { '' } else { Find-AppBrowser }
    try {
        if ($exe) {
            Start-Process -FilePath $exe -ArgumentList @(("--app=" + $Url), '--no-first-run', '--no-default-browser-check') | Out-Null
            Write-Ok 'page     opened in its own window (reused server)'
        }
        else { Start-Process $Url | Out-Null; Write-Ok 'page     opened in the default browser' }
    }
    catch { Write-Info ("page     could not be opened: " + $_.Exception.Message) }
}

function Start-WebWindow {
    # Serve hidden in the background: the server runs directly (python ... web) with its
    # output redirected into the work log folder, so no console window is left behind.
    # `status` and `stop` find it by the command line, which still says `-m core.cli ... web`.
    Write-Head 'web ui (background)'
    if (-not (Test-Path $Python)) { Write-Bad "python not found: $Python"; return 2 }
    if (-not (Test-Path $Cli)) { Write-Bad "cli not found: $Cli"; return 2 }
    if ($Port -le 0) {
        # no port named: reuse the instance this editor records, else take the first free port.
        # The CLI picks the same way when it is started without port=, so both stay in step.
        $running = Read-WebInstance
        if ($running) {
            $Port = [int]$running.port
            Write-Ok ("reusing the instance already running (pid " + $running.pid + ")")
            Write-Info ("url      " + $running.url)
            Open-ReusedPage $running.url
            return 0
        }
        $Port = Find-FreePort $script:DefaultPort
        Write-Info ("port      none named - first free one: " + $Port)
    }
    if (Test-PortOpen $Port) {
        Write-Bad ("port {0} is already in use - an older server is probably still running (pid {1})" -f $Port, (Get-PortOwner $Port))
        Write-Info 'close it from its page (退出), or run:  stop'
        Write-Info ("or start this one elsewhere:  ff-tool.cmd web -Window -Port " + ($Port + 1))
        return 2
    }

    # the server log lives next to the launcher log, not in out/, so `stop` does not erase it
    $logDir = Split-Path $script:LogFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    $outLog = Join-Path $logDir ("web-{0}-out.log" -f $Port)
    $errLog = Join-Path $logDir ("web-{0}-err.log" -f $Port)
    # quoted so a path with a space survives; the CLI takes key=value pairs, so a quoted whole
    # argument is also what Python's argv needs (the shell is not involved here)
    $scopeName = Get-WebScope
    $scopeRoot = if ($Project) { $Project } elseif ($scopeName -eq 'Firefight') { $Root } else { '' }
    $rootArgs = @(Get-WebRootArgs $scopeName | ForEach-Object { '"' + $_ + '"' })
    $cliArgs = @('-m', 'core.cli', $scopeName, 'web') + $rootArgs + @('"port=' + $Port + '"')
    try {
        $proc = Start-Process -FilePath $Python -ArgumentList $cliArgs -WorkingDirectory $editorRoot `
            -WindowStyle Hidden -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog
    }
    catch { Write-Bad ("could not start the server: " + $_.Exception.Message); return 1 }

    $url = "http://127.0.0.1:{0}/" -f $Port
    Write-Info ("python   " + $Python)
    Write-Info ("cli      python -m core.cli  (" + $Cli + ")")
    Write-Info ("scope    " + $scopeName)
    Write-Info ("root     " + (Get-WebRootText $scopeName))
    Write-Info ("server   pid " + $proc.Id + " (no window)")
    Write-Info ("log      " + $errLog)
    $ready = $false
    for ($try = 0; $try -lt 40; $try++) {
        if (Test-PortOpen $Port) { $ready = $true; break }
        Start-Sleep -Milliseconds 250
    }
    if ($ready) {
        # The port answers: make sure it is the server this tool just started. The instance
        # record the CLI writes names that pid exactly and needs no WMI, which is unavailable in
        # locked-down sessions; the leftover checks stay as a fallback for older entry points.
        $owner = Get-PortOwner $Port
        $ours = $false
        $how = 'process name'
        $record = Read-WebInstance
        if ($record -and ([int]$record.pid -eq $proc.Id)) { $ours = $true; $how = 'instance record' }
        elseif ($owner -gt 0) {
            $who = Get-CimInstance -ClassName Win32_Process -Filter ("ProcessId = " + $owner) -ErrorAction SilentlyContinue
            if ($who -and $who.CommandLine) {
                # the exact check; WMI can be unavailable in locked-down sessions, then fall back
                $ours = ($who.CommandLine -match '(ff\.py|m\s+core\.cli)' -and $who.CommandLine -match '\sweb(\s|$)')
                $how = 'command line'
            }
            else {
                $name = (Get-Process -Id $owner -ErrorAction SilentlyContinue).ProcessName
                $ours = ($name -match '^python')
            }
        }
        if ($ours) { Write-Ok ("listening on " + $url + " (pid " + $owner + ", checked by " + $how + ")") }
        else {
            Write-Bad ("port {0} is answered by pid {1}, which is not this server" -f $Port, $owner)
            Write-Info 'that process was already there - close it, or start on another port with -Port'
            $ready = $false
            # do not leave the server this tool just started running behind a failed check
            if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
        }
    }
    else { Write-Bad ("nothing answered on port {0} after 10 s" -f $Port) }
    if (-not $ready) {
        Write-Info 'the server writes its errors to the log above - read the last lines:'
        if (Test-Path $errLog) { Get-Content $errLog -Tail 12 | ForEach-Object { Write-Info ("  " + $_) } }
        Write-Info 'run `stop` to clean up, or try another port with -Port'
        return 1
    }


    # the server is up: show the page. Default is a Chromium app window (no tabs, no address
    # bar), -Browser uses the default browser instead, -NoBrowser opens nothing.
    $pagePid = 0
    $profileDir = ''
    $browserBefore = ''
    $pageMode = 'none'
    # declared here, not inside the branch below: the watchdog arguments must never be empty
    $dbgPort = 0
    if ($NoBrowser) { Write-Info 'page     not opened (-NoBrowser) - the address is above' }
    else {
        $exe = if ($Browser) { '' } else { Find-AppBrowser }
        if ($exe) {
            # A profile of its own, under TEMP: the window is then a browser process nobody
            # else uses, and `stop` wipes out\ while the window may still be open.
            $profileDir = Join-Path $env:TEMP ("ff-tool-web-{0}" -f $Port)
            if (-not (Test-Path $profileDir)) { New-Item -ItemType Directory -Path $profileDir -Force | Out-Null }
            # Chromium may hand a fresh profile over to another process, so the browser
            # processes that exist beforehand are recorded for Close-PageWindow.
            $browserBefore = (Get-BrowserPids) -join ','
            # a debugging port of its own: the watchdog can then tell whether the window is
            # still up, and it stays on 127.0.0.1
            for ($k = 1; $k -le 20; $k++) { if (-not (Test-PortOpen ($Port + $k))) { $dbgPort = $Port + $k; break } }
            try {
                $pageArgs = @(("--app=" + $url), ("--user-data-dir=" + $profileDir),
                    '--no-first-run', '--no-default-browser-check')
                if ($dbgPort -gt 0) { $pageArgs += ("--remote-debugging-port=" + $dbgPort) }
                $page = Start-Process -FilePath $exe -PassThru -ArgumentList $pageArgs
                $pagePid = $page.Id
                $pageMode = 'app'
                Write-Ok ("page     opened in its own window (" + [System.IO.Path]::GetFileName($exe) + " --app)")
                # Wait until the window is up: <profile>\lockfile is held open for as long as
                # the window lives; the debugging port is the fallback when a browser does
                # not create the lock.
                $up = $false
                for ($k = 0; $k -lt 60; $k++) {
                    if ((Test-ProfileLocked $profileDir) -or ($dbgPort -gt 0 -and (Test-PortOpen $dbgPort))) { $up = $true; break }
                    Start-Sleep -Milliseconds 250
                }
                if ($up -and (Test-ProfileLocked $profileDir)) { Write-Info 'window   up, watched through its profile lock' }
                elseif ($up) { Write-Info ("window   up, watched through port {0}" -f $dbgPort) }
                else {
                    Write-Info 'window   did not come up in 15 s - the page window will not be watched'
                    $pageMode = 'browser'
                }
            }
            catch { Write-Bad ("could not start " + $exe + ": " + $_.Exception.Message) }
        }
        else {
            if (-not $Browser) { Write-Info 'no Edge/Chrome found - opening the default browser instead' }
            try {
                Start-Process $url | Out-Null
                $pageMode = 'browser'
                Write-Ok 'page     opened in the default browser'
                Write-Info 'that window belongs to the user''s own browser and is never closed by this tool'
            }
            catch { Write-Bad ("could not open the browser: " + $_.Exception.Message) }
        }
    }

    # a hidden watchdog stays with the session: when the server stops it checks how it stopped
    # and closes the page window this tool opened (see the `watch` action)
    $watchPid = 0
    try {
        # 'NONE' stands in for an empty argument: Start-Process refuses a null or empty element,
        # and a bare '-' would be taken for a parameter name when the script splats its argv
        $none = 'NONE'
        $watchArgs = @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
            '-File', $script:Self, 'watch', "$Port", "$($proc.Id)", "$pagePid",
            $(if ($outLog) { $outLog } else { $none }),
            $(if ($errLog) { $errLog } else { $none }),
            $(if ($url) { $url } else { $none }),
            $(if ($profileDir) { $profileDir } else { $none }),
            $pageMode,
            $(if ($browserBefore) { $browserBefore } else { $none }),
            "$dbgPort")
        $watch = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $watchArgs `
            -WorkingDirectory $WorkDir -WindowStyle Hidden -PassThru
        $watchPid = $watch.Id
        Write-Info ("watchdog pid " + $watchPid + " (checks the exit, then closes the page window)")
    }
    catch { Write-Info ("could not start the watchdog: " + $_.Exception.Message) }

    $state = [ordered]@{
        pid = $proc.Id; url = $url; port = $Port; scope = $scopeName; python = $Python; cli = $Cli
        root = $scopeRoot; outLog = $outLog; errLog = $errLog
        page = $pagePid; profile = $profileDir; watchdog = $watchPid; browserBefore = $browserBefore
        watchPort = $dbgPort
        startedAt = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    }
    $state | ConvertTo-Json | Set-Content -Path $script:WebStateFile -Encoding UTF8
    Write-Info ("state    " + $script:WebStateFile)
    Write-Info 'nothing else is left open: no console window, only the page above'
    Write-Info 'closing the page (退出) stops the server too, and the page window closes with it'
    Write-Info 'closing the app window also stops the server (checked through its profile lock)'
    return 0
}

function Show-WebState {
    Write-Head 'web ui'
    $logDir = Split-Path $script:LogFile -Parent
    $exitLog = Join-Path $logDir ("web-{0}-exit.log" -f $Port)
    if (-not (Test-Path $script:WebStateFile)) {
        Write-Info 'not running (start one with: web-open, or ff-tool.cmd web -Window)'
        # no session recorded: report the newest exit log there is, whatever port it ran on
        $newest = Get-ChildItem $logDir -Filter 'web-*-exit.log' -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime | Select-Object -Last 1
        if ($newest) {
            $last = @(Get-Content $newest.FullName | Where-Object { $_.Trim() })[-1]
            Write-Info ("last session  " + $last)
        }
        return
    }
    $state = Get-Content $script:WebStateFile -Raw | ConvertFrom-Json
    $webPort = if ($state.port) { [int]$state.port } else { $Port }
    if ($state.port) { $exitLog = Join-Path $logDir ("web-{0}-exit.log" -f $webPort) }
    if (Test-PortOpen $webPort) {
        Write-Ok ("listening on http://127.0.0.1:{0}/ (since {1})" -f $webPort, $state.startedAt)
        # the state file knows the pids even where WMI is denied, so ask it first and only
        # fall back to the command-line search and the port owner when the pid is gone
        $serverPid = 0
        if ($state.pid) { $serverPid = [int]$state.pid }
        if ($serverPid -gt 0 -and (Get-Process -Id $serverPid -ErrorAction SilentlyContinue)) {
            Write-Info ("server   pid " + $serverPid + " (no window)")
        }
        else {
            $mine = @(Get-FfWeb)
            if ($mine) { foreach ($p in $mine) { Write-Info ("server   pid " + $p.ProcessId + " (no window)") } }
            else { Write-Info ("owner    pid " + (Get-PortOwner $webPort) + " (not a process this tool started)") }
        }
        if ($state.errLog) { Write-Info ("log      " + $state.errLog) }
        $watchPid = 0
        if ($state.watchdog) { $watchPid = [int]$state.watchdog }
        if ($watchPid -gt 0 -and (Get-Process -Id $watchPid -ErrorAction SilentlyContinue)) {
            Write-Info ("watchdog pid " + $watchPid + " (checks the exit, closes the page window)")
        }
        else {
            $watch = @(Get-FfWatch)
            if ($watch) { Write-Info ("watchdog pid " + $watch[0].ProcessId + " (checks the exit, closes the page window)") }
        }
        if ($state.page -and (Get-Process -Id ([int]$state.page) -ErrorAction SilentlyContinue)) {
            Write-Info ("page     window pid " + $state.page + " (closing it stops the server)")
        }
        Write-Info 'the page has a 退出 button; `stop` closes it too'
    }
    else {
        Write-Info ("nothing is listening on port {0} - the ui is not running" -f $webPort)
        if (Test-Path $script:WebStateFile) { Write-Info 'stale state file (`stop` clears it)' }
        if ($exitLog -and (Test-Path $exitLog)) {
            $last = @(Get-Content $exitLog | Where-Object { $_.Trim() })[-1]
            Write-Info ("last session  " + $last)
        }
    }
}

function Stop-IfOurs([int]$ProcessId, [string]$Expect) {
    # Refuse to end a process whose name does not match $Expect: a state file can outlive its
    # process, and the recorded pid can belong to something else. The command line needs WMI,
    # so the process name is the portable check.
    if (-not $ProcessId) { return $false }
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) { return $false }
    if ($Expect -and ($proc.ProcessName -notmatch $Expect)) {
        Write-Info ("pid {0} is {1}, not {2} - a reused pid, leaving it alone" -f $ProcessId, $proc.ProcessName, $Expect)
        return $false
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    return $true
}

function Stop-Tool {
    Write-Head 'processes'
    foreach ($p in @(Get-FfWeb)) {
        Write-Info ("ending web ui pid {0}" -f $p.ProcessId)
        Write-Log ("kill web pid {0}" -f $p.ProcessId)
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    $procs = Get-FfPython
    if ($procs) {
        foreach ($p in $procs) {
            Write-Info ("ending pid {0}: {1}" -f $p.ProcessId, $p.CommandLine)
            Write-Log ("kill pid {0}" -f $p.ProcessId)
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Write-Ok ("ended {0} editor process(es)" -f @($procs).Count)
    }
    else { Write-Ok 'no editor process was running' }

    Write-Head 'work directory'
    if (Test-Path $script:OutDir) {
        if ($KeepOutput) { Write-Info "kept     $script:OutDir (-KeepOutput)" }
        else {
            $size = (Get-ChildItem $script:OutDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
            try { Remove-Item $script:OutDir -Recurse -Force } catch { Write-Info ("some files are still in use: " + $_.Exception.Message) }
            Write-Ok ("removed  {0} ({1} B)" -f $script:OutDir, [int]$size)
        }
    }
    else { Write-Info "nothing to clean in $script:OutDir" }

    if (Test-Path $script:StateFile) { Remove-Item $script:StateFile -Force; Write-Ok "removed  $script:StateFile" }

    if (Test-Path $script:WebStateFile) {
        $web = Get-Content $script:WebStateFile -Raw | ConvertFrom-Json
        # A background server has no window, so end it by pid as well when Get-FfWeb did not
        # recognise its command line (a different python, a renamed script); Stop-IfOurs
        # checks that the pid is still a python process.
        if ($web.pid -and (Get-Process -Id $web.pid -ErrorAction SilentlyContinue)) {
            Write-Info ("ending background server pid {0}" -f $web.pid)
            Stop-IfOurs ([int]$web.pid) 'python' | Out-Null
        }
        Remove-Item $script:WebStateFile -Force
        Write-Ok "removed  $script:WebStateFile"
        # Wait for the recorded watchdog pid (WMI, which Get-FfWatch needs, is not always
        # available): it sees the server is gone, records the exit and closes the page window.
        if ($web.watchdog -and (Get-Process -Id $web.watchdog -ErrorAction SilentlyContinue)) {
            for ($j = 0; $j -lt 40; $j++) {
                if (-not (Get-Process -Id $web.watchdog -ErrorAction SilentlyContinue)) { break }
                Start-Sleep -Milliseconds 250
            }
        }
        if ($web.watchdog -and (Get-Process -Id $web.watchdog -ErrorAction SilentlyContinue)) {
            Write-Info ("ending watchdog pid {0}" -f $web.watchdog)
            Stop-IfOurs ([int]$web.watchdog) 'powershell|pwsh' | Out-Null
        }
        foreach ($p in @(Get-FfWatch)) {
            Write-Info ("ending watchdog pid {0}" -f $p.ProcessId)
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
        if ($web.page -and (Get-Process -Id $web.page -ErrorAction SilentlyContinue)) {
            Write-Info ("closing page window pid {0}" -f $web.page)
            Stop-IfOurs ([int]$web.page) 'msedge|chrome' | Out-Null
        }
        if ($web.profile -and (Test-Path $web.profile)) {
            # the browser profile of that window is disposable, and only this tool uses it
            for ($k = 0; $k -lt 6; $k++) {
                try { Remove-Item $web.profile -Recurse -Force -ErrorAction Stop; break } catch { Start-Sleep -Milliseconds 400 }
            }
            if (Test-Path $web.profile) { Write-Info ("kept the browser profile: " + $web.profile) }
        }
    }
    Write-Head 'closed'
    Write-Ok ('log kept at ' + $script:LogFile)
}

function Show-Status {
    Write-Head 'paths'
    $rows = @(
        @{ name = 'python'; path = $Python },
        @{ name = 'cli'; path = $Cli },
        @{ name = 'stock'; path = $Root },
        @{ name = 'workdir'; path = $WorkDir },
        @{ name = 'output'; path = $script:OutDir }
    )
    if ($Project) { $rows += @{ name = 'project'; path = $Project } }
    foreach ($row in $rows) {
        $line = "{0,-8} {1}" -f $row.name, $row.path
        if (Test-Path $row.path) { Write-Ok $line }
        elseif ($row.name -eq 'output') { Write-Info ("{0} (not created yet)" -f $line) }
        else { Write-Bad $line }
    }
    if (-not $Project) { Write-Info 'project  (none) - Mod scope needs -Project <dir with ModInformation.toml>' }

    Write-Head 'running'
    $procs = Get-FfPython
    if ($procs) { foreach ($p in $procs) { Write-Info ("pid {0}: {1}" -f $p.ProcessId, $p.CommandLine) } }
    else { Write-Info 'no editor process is running (the CLI is one-shot, so this is the normal state)' }

    Write-Head 'state'
    if (Test-Path $script:StateFile) {
        $state = Get-Content $script:StateFile -Raw | ConvertFrom-Json
        Write-Info ("started  {0} (pid {1})" -f $state.startedAt, $state.pid)
    }
    else { Write-Info 'no state file - the tool has not been started (or was stopped)' }

    Show-WebState

    if (Test-Path $script:LogFile) {
        $size = (Get-Item $script:LogFile).Length
        Write-Info ("log      {0} ({1} B)" -f $script:LogFile, $size)
        Write-Info 'last 5 lines:'
        Get-Content $script:LogFile -Tail 5 | ForEach-Object { Write-Info ("  " + $_) }
    }
    else { Write-Info 'no log yet' }
}

function Get-FfWatch {
    # the hidden watchdog processes this tool starts, one per background web session
    Get-CimInstance -ClassName Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'ff-tool\.ps1' -and $_.CommandLine -match '\swatch\s' }
}

function Get-BrowserPids {
    @(Get-Process msedge, chrome -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
}

function Test-ProfileLocked([string]$Profile) {
    # Output: true while another process holds <Profile>\lockfile open, which a Chromium
    # window does for as long as it lives. Needs neither WMI nor a debugging port.
    if (-not $Profile) { return $false }
    $file = Join-Path $Profile 'lockfile'
    if (-not (Test-Path $file)) { return $false }
    try {
        $stream = [System.IO.File]::Open($file, 'Open', 'ReadWrite', 'None')
        $stream.Close()
        return $false
    }
    catch { return $true }
}

function Test-WindowAlive([string]$Profile, [int]$DbgPort, [int]$PagePid) {
    # Output: true while the page window this tool opened is still there. A browser process
    # that appeared after the start is no signal: the user's own window would keep a closed
    # session alive.
    if (Test-ProfileLocked $Profile) { return $true }
    if ($DbgPort -gt 0 -and (Test-PortOpen $DbgPort)) { return $true }
    if ($PagePid -gt 0 -and (Get-Process -Id $PagePid -ErrorAction SilentlyContinue)) { return $true }
    return $false
}

function Close-PageWindow([string]$Url, [int]$PagePid, [string]$Profile, [string]$Pids) {
    # Close only the app window this tool opened, most exact match first: (1) the command
    # line carries --app=<url> or --user-data-dir=<profile> (WMI), (2) the recorded pid,
    # (3) a browser process that was not there beforehand — the window uses a profile of its
    # own, so everything new is ours. WMI is unavailable in a locked-down session.
    $killed = 0
    $patterns = @()
    if ($Url) { $patterns += [regex]::Escape('--app=' + $Url) }
    if ($Profile) { $patterns += [regex]::Escape('--user-data-dir=' + $Profile) }
    if ($patterns.Count -gt 0) {
        $procs = @(Get-CimInstance -ClassName Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $line = $_.CommandLine; $line -and ($patterns | Where-Object { $line -match $_ }) })
        foreach ($p in $procs) {
            try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; $killed++ } catch { }
        }
        if ($killed -gt 0) { return ("closed, {0} process(es) by command line" -f $killed) }
    }
    if ($PagePid -gt 0 -and (Get-Process -Id $PagePid -ErrorAction SilentlyContinue)) {
        try { Stop-Process -Id $PagePid -Force -ErrorAction Stop; $killed++ } catch { }
    }
    $known = @()
    if ($Pids) { $known = @($Pids -split ',' | Where-Object { $_ -ne '' } | ForEach-Object { [int]$_ }) }
    $new = @(Get-Process msedge, chrome -ErrorAction SilentlyContinue |
        Where-Object { $known -notcontains $_.Id -and $_.Id -ne $PagePid })
    foreach ($p in $new) {
        try { Stop-Process -Id $p.Id -Force -ErrorAction Stop; $killed++ } catch { }
    }
    if ($killed -gt 0) { return ("closed, {0} process(es)" -f $killed) }
    if (-not $Url -and $PagePid -eq 0) { return 'none opened' }
    return 'was already gone'
}

function Watch-Web([string]$PortArg, [string]$ServerPidArg, [string]$PagePidArg, [string]$OutLogArg, [string]$ErrLogArg, [string]$UrlArg, [string]$ProfileArg, [string]$PageModeArg, [string]$PidsArg, [string]$DbgPortArg) {
    # Watch one web session to its end and clean up after it.
    # Forwards: when the server stops (退出 on the page, `stop`, Ctrl-C, a crash), close the
    # app window and delete its throw-away profile; the verdict is appended to
    # web-<port>-exit.log, which `status` shows as the last session.
    # Reverse: with PageModeArg 'app', three dead checks in a row mean the user closed the
    # window first, and the server is then asked to leave through /quit (see Test-WindowAlive
    # for the signal). In 'browser' mode the window belongs to the user's own browser and is
    # never touched; in 'none' mode there is no window.
    $serverPid = [int]$ServerPidArg
    $pagePid = [int]$PagePidArg
    $webPort = [int]$PortArg
    $dbgPort = 0
    if ($DbgPortArg) { $dbgPort = [int]$DbgPortArg }
    # Start-Process cannot carry an empty argument, so the caller sends 'NONE' for "not there"
    foreach ($name in @('OutLogArg', 'ErrLogArg', 'UrlArg', 'ProfileArg', 'PidsArg')) {
        if ((Get-Variable -Name $name -ValueOnly) -eq 'NONE') { Set-Variable -Name $name -Value '' }
    }
    $logDir = Split-Path $script:LogFile -Parent
    $exitLog = Join-Path $logDir ("web-{0}-exit.log" -f $webPort)
    $reason = ''
    $misses = 0
    for ($i = 0; $i -lt 43200; $i++) {
        if (-not (Get-Process -Id $serverPid -ErrorAction SilentlyContinue)) { $reason = 'the server stopped'; break }
        if ($PageModeArg -eq 'app') {
            if (Test-WindowAlive $ProfileArg $dbgPort $pagePid) { $misses = 0 }
            else {
                # three checks about five seconds apart: a window that is merely slow to
                # answer is not a closed window
                $misses++
                if ($misses -ge 3) {
                    $reason = 'the page window was closed first'
                    # ask the server to stop the polite way, so its log keeps the graceful
                    # marker and the verdict below reads "backend exited normally"
                    try { Invoke-WebRequest -Uri ($UrlArg + 'quit?do=1') -UseBasicParsing -TimeoutSec 5 | Out-Null } catch { }
                    for ($j = 0; $j -lt 25; $j++) {
                        if (-not (Get-Process -Id $serverPid -ErrorAction SilentlyContinue)) { break }
                        Start-Sleep -Milliseconds 200
                    }
                    break
                }
            }
        }
        Start-Sleep -Seconds 2
    }
    if (-not $reason) { $reason = 'the watchdog gave up after 24 hours' }
    $alive = [bool](Get-Process -Id $serverPid -ErrorAction SilentlyContinue)
    $portOpen = Test-PortOpen $webPort
    $graceful = $false
    foreach ($file in @($OutLogArg, $ErrLogArg)) {
        if ($file -and (Test-Path $file)) {
            # the marker is ASCII, so no code page can hide it from this match
            if ((Get-Content $file -Raw -ErrorAction SilentlyContinue) -match 'web: stopped by the quit link') { $graceful = $true }
        }
    }
    $window = if ($PageModeArg -eq 'app') { Close-PageWindow $UrlArg $pagePid $ProfileArg $PidsArg } else { 'no window of ours' }
    if ((-not $alive) -and (-not $portOpen) -and $graceful) { $verdict = 'backend exited normally' }
    elseif ((-not $alive) -and (-not $portOpen)) { $verdict = 'backend exited, but without the quit marker (killed?)' }
    elseif ($alive) { $verdict = 'backend is STILL RUNNING' }
    else { $verdict = 'the process is gone but the port still answers' }
    $line = "{0} :: port {1} :: {2} :: graceful {3} :: page window {4} :: {5}" -f `
        (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $webPort, $reason, $graceful, $window, $verdict
    try { Add-Content -Path $exitLog -Value $line -Encoding UTF8 } catch { }
    Write-Log ("watch: " + $line)
    # the session is over, so the state file it left should not outlive it — but only clear it
    # while it still describes *this* server: a newer session may have started since
    try {
        if (Test-Path $script:WebStateFile) {
            $state = Get-Content $script:WebStateFile -Raw | ConvertFrom-Json
            if ([int]$state.pid -eq $serverPid) {
                Remove-Item $script:WebStateFile -Force -ErrorAction Stop
                Write-Log 'watch: cleared the state file'
            }
        }
    }
    catch { }
    if ($ProfileArg -and (Test-Path $ProfileArg)) {
        # the window is gone, so its disposable browser profile can go as well; a browser keeps
        # the last handles for a moment after the process ends, hence the retries
        for ($k = 0; $k -lt 6; $k++) {
            try { Remove-Item $ProfileArg -Recurse -Force -ErrorAction Stop; break } catch { Start-Sleep -Milliseconds 400 }
        }
    }
    return $(if ($verdict -eq 'backend exited normally') { 0 } else { 1 })
}

function Show-Help {
    Write-Head 'ff-tool'
    Write-Info 'ff-tool.cmd [action] [options]        (double-click runs: start)'
    Write-Info 'actions:'
    Write-Info '  start    preflight, show the editor version and the stock scope, leave `ff` ready'
    Write-Info '  stop     end leftover editor processes and clean the output directory'
    Write-Info '  restart  stop then start'
    Write-Info '  status   paths, running processes, state file, log tail'
    Write-Info '  run      everything after it goes to the CLI, e.g. run Firefight stats --json'
    Write-Info '  web      serve the read-only web UI for the stock data until Ctrl-C (see below)'
    Write-Info 'options: -Quick (skip the stock scan)  -KeepOutput  -Project <dir>  -Port <n>'
    Write-Info '         -Window (web: serve in the background)  -NoBrowser  -Browser'
    Write-Info '         -Python <exe>  -Cli <core\cli\__main__.py>  -Root <game dir>  -WorkDir <dir>'
    Write-Head 'inside a started window'
    Write-Info 'status | stop | restart              the same actions, typed at the prompt'
    Write-Info 'ff-start                             start again (PowerShell owns the name `start`)'
    Write-Info 'web                                  web UI in this window; Ctrl-C stops it'
    Write-Info 'web-open                             web UI in the background, page in its own window'
    Write-Info 'ff <CLI args>                        the CLI itself, e.g. ff Firefight stats --json (root is added for Firefight)'
    Write-Head 'the web ui'
    Write-Info 'ff-tool.cmd web                      in this window, Ctrl-C to stop (browser opens)'
    Write-Info 'ff-tool.cmd web -Window              server hidden, page in a plain app window'
    Write-Info 'ff-tool.cmd web -Window -NoBrowser   server only - open the address yourself'
    Write-Info 'ff-tool.cmd web -Window -Browser     use the normal browser window instead'
    Write-Info 'binds 127.0.0.1 only, one request at a time, no JavaScript, read-only'
    Write-Info 'pages  首页 / 实体列表 / 实体详情 / 查找 / 引用 / 体检 / 统计 / 命令行 / 帮助 / JSON / 退出'
    Write-Info 'stop it from the page (退出, asks once) or with:  stop'
    Write-Info 'a hidden watchdog checks the exit, then closes the app window it opened: 退出 ends both'
    Write-Info 'closing that window yourself stops the server too; -Browser opens the default browser instead'
    Write-Info 'and is not watched; -Scope <name> picks the scope (default Firefight, Mod with -Project)'
    Write-Info 'options port=<n> (8765) -Port <n>, token=<text> (add ?t=<text>), pagesize=<n> (200), browser=1'
    Write-Head 'the CLI itself'
    Write-Info 'ff <scope> <command> [selector] [key=value ...] [--json]'
    Write-Info 'scope   Firefight (stock game data) | Mod (the project with ModInformation.toml) | a mod folder name'
    Write-Info 'command check, deps, export, find, get, list, refs, show, stats, version, web   (all'
    Write-Info '        read-only except export, which writes only under to=; there is no edit command yet)'
    Write-Info 'exit    0 ok | 1 executed failure (the JSON payload is still valid) | 2 usage error'
    Write-Info 'the Firefight scope gets root= added by the tool; other scopes need a real root=<dir>'
}

Initialize-Log
$script:ExitCode = 0
switch ($Action) {
    'start' { $null = Start-Tool }
    'stop' { Stop-Tool }
    'restart' { Stop-Tool; $null = Start-Tool }
    'status' { Show-Status }
    'run' {
        if (-not $Rest -or $Rest.Count -eq 0) { Write-Bad 'run needs CLI arguments, e.g. run Firefight stats --json' }
        else { $null = Invoke-Ff $Rest }
    }
    'web' {
        # keep the exit code so ff-tool.cmd can pause on a failure (a taken port, no server)
        if ($Window) { $script:ExitCode = Start-WebWindow } else { $script:ExitCode = Start-Web }
    }
    'watch' {
        # internal: the hidden watchdog of a background web session (see Watch-Web). Bound
        # position by position, because splatting would read a leading dash as a parameter.
        if (-not $Rest -or $Rest.Count -lt 6) { $script:ExitCode = 2 }
        else { $script:ExitCode = Watch-Web $Rest[0] $Rest[1] $Rest[2] $Rest[3] $Rest[4] $Rest[5] $Rest[6] $Rest[7] $Rest[8] $Rest[9] }
    }
    'help' { Show-Help }
}

# In-shell verbs, registered globally so they survive in a window opened with -NoExit.
# `start` is a read-only AllScope alias for Start-Process, so the start action is `ff-start`
# and only the free names get a short alias.
if ($Action -eq 'start' -or $Action -eq 'restart' -or $Action -eq 'web') {
    foreach ($name in @('start', 'stop', 'restart', 'status')) {
        Set-Item -Path "function:global:ff-$name" -Value ([scriptblock]::Create("& '$($script:Self)' $name @args")) -Force
    }
    Set-Item -Path 'function:global:ff-web' -Value ([scriptblock]::Create(
        "if (`$args -contains '-Port') { & '$($script:Self)' web @args } else { & '$($script:Self)' web -Port $Port @args }")) -Force
    Set-Item -Path 'function:global:web-open' -Value ([scriptblock]::Create(
        "if (`$args -contains '-Port') { & '$($script:Self)' web -Window @args } else { & '$($script:Self)' web -Window -Port $Port @args }")) -Force
    foreach ($name in @('stop', 'restart', 'status')) {
        Set-Alias -Name $name -Value "ff-$name" -Scope Global -Force -ErrorAction SilentlyContinue
    }
    if (-not (Get-Alias -Name 'web' -ErrorAction SilentlyContinue)) {
        Set-Alias -Name 'web' -Value 'ff-web' -Scope Global -Force -ErrorAction SilentlyContinue
    }
}

if ($script:ExitCode -ne 0) { exit $script:ExitCode }
