param([ValidateSet('start','stop')][string]$Action = 'start')
$ErrorActionPreference = 'Stop'
# PS7 -> Python/cmd -> Windows PowerShell inherits incompatible Core modules.
# This self-contained launcher needs only this runtime's built-in modules;
# restrict discovery in this process, including direct -File invocations.
$env:PSModulePath = "$PSHOME\Modules"
Set-Location -LiteralPath $PSScriptRoot
foreach ($name in @('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
function Docker-Checked([string[]]$Arguments) {
    $result = & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker failed (exit $LASTEXITCODE). Start Docker Desktop in Linux mode." }
    return $result
}
# The installation directory must be trusted and not concurrently replaced.
# These leaf checks reject existing reparse paths; they are not an atomic
# handle-based defense against an attacker able to race directory/file changes.
function Assert-PlainFile([string]$Path) {
    try { $attributes = [System.IO.File]::GetAttributes($Path) }
    catch [System.IO.FileNotFoundException] { return }
    catch [System.IO.DirectoryNotFoundException] { return }
    if ($attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'Reparse points are not allowed for private files.' }
    if ($attributes -band [System.IO.FileAttributes]::Directory) { throw 'Private file path is a directory.' }
}
function Set-PrivateFile([string]$Path) {
    Assert-PlainFile $Path
    # Intentional replacement policy, not an owner-only edit of an inherited
    # DACL (which can contain OWNER RIGHTS): current user owns and alone has access.
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = New-Object System.Security.AccessControl.FileSecurity
    $acl.SetOwner($user)
    $acl.SetAccessRuleProtection($true,$false)
    $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($user,'FullControl','Allow')))
    Set-Acl -LiteralPath $Path -AclObject $acl
    $actual = Get-Acl -LiteralPath $Path
    $rules = @($actual.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]))
    if ($actual.GetOwner([System.Security.Principal.SecurityIdentifier]) -ne $user -or
        -not $actual.AreAccessRulesProtected -or $rules.Count -ne 1 -or
        $rules[0].IdentityReference -ne $user -or $rules[0].AccessControlType -ne 'Allow' -or
        $rules[0].FileSystemRights -ne 'FullControl') { throw 'Cannot establish private file permissions.' }
}
try {
    $context = (Docker-Checked @('context','show') | Out-String).Trim()
    $endpoint = (Docker-Checked @('context','inspect',$context,'--format','{{.Endpoints.docker.Host}}') | Out-String).Trim()
    if ($endpoint -cmatch '\Anpipe:////\./pipe/[a-zA-Z0-9_-]+\z') { $env:POD_RELEASE_SOCKET = '/var/run/docker.sock' }
    elseif ($endpoint -cmatch '\Aunix://(/[a-zA-Z0-9_.-]+)+\z' -and $endpoint -cnotmatch '/\.\.?(/|\z)') { $env:POD_RELEASE_SOCKET = $endpoint.Substring(7) }
    else { throw 'Only local Docker Desktop/Unix contexts are supported. Select a local context.' }
    if ((Docker-Checked @('--context',$context,'info','--format','{{.OSType}}') | Out-String).Trim() -ne 'linux') { throw 'Select Linux containers in Docker Desktop.' }
    $serverOS = (Docker-Checked @('--context',$context,'info','--format','{{.OperatingSystem}}') | Out-String).Trim()
    if ($serverOS -ceq 'Docker Desktop') {
        # Bind sources belong to the daemon VM, not the Desktop client socket:
        # https://docs.docker.com/engine/storage/bind-mounts/#considerations-and-constraints
        $env:POD_RELEASE_SOCKET = '/var/run/docker.sock'
    } elseif ($serverOS -eq '' -or $serverOS -eq '<no value>') { throw 'Cannot identify the Docker server operating system.' }
    elseif ($endpoint.StartsWith('npipe:')) { throw 'Named pipes require Docker Desktop.' }
    Docker-Checked @('--context',$context,'compose','version') | Out-Null
    $state = Join-Path $PSScriptRoot '.classroom-project'
    Assert-PlainFile $state
    $newId = $null
    if (-not (Test-Path -LiteralPath $state)) {
        if ($Action -ne 'start') { throw 'No saved classroom project.' }
        $newId = 'pod-public-' + [guid]::NewGuid().ToString('N')
        $stream = [System.IO.File]::Open($state, [System.IO.FileMode]::CreateNew)
        $stream.Dispose()
    }
    Set-PrivateFile $state
    if ($null -ne $newId) { [System.IO.File]::WriteAllText($state, $newId + "`n", [System.Text.Encoding]::ASCII) }
    $project = [System.IO.File]::ReadAllText($state).Trim()
    if ($project -cnotmatch '\Apod-public-[0-9a-f]{32}\z') { throw 'Invalid project file. Refusing to run.' }
    $common = @('--context',$context,'compose','--project-name',$project,'--env-file','compose.defaults','-f','compose.yaml')
    if ($Action -eq 'stop') {
        Docker-Checked ($common + @('stop'))
        Write-Host 'Stopped. Classroom data is preserved.'
    } else {
        Docker-Checked ($common + @('pull'))
        Docker-Checked ($common + @('up','--no-build','-d','--wait','--wait-timeout','180'))
        $log = Join-Path $PSScriptRoot 'teacher-private.log'
        Assert-PlainFile $log
        # Establish private ownership and DACL before truncating an existing log
        # or writing any teacher secret. New files start empty.
        if (-not (Test-Path -LiteralPath $log)) {
            $stream = [System.IO.File]::Open($log, [System.IO.FileMode]::CreateNew)
            $stream.Dispose()
        }
        Set-PrivateFile $log
        [System.IO.File]::WriteAllText($log, '')
        Docker-Checked ($common + @('logs','--no-color','classroom')) | Set-Content -LiteralPath $log
        Write-Host 'Teacher: http://localhost:8765/teacher'
        Write-Host 'Projector: http://localhost:8765/projector'
        Write-Host 'Keep teacher-private.log private: it contains the teacher key.'
    }
} catch { Write-Error $_; exit 1 }
