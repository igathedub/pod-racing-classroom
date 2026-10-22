param([ValidateSet('start','stop')][string]$Action = 'start')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
foreach ($name in @('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
function Docker-Checked([string[]]$Arguments) {
    $result = & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker failed (exit $LASTEXITCODE). Start Docker Desktop in Linux mode." }
    return $result
}
try {
    $context = (Docker-Checked @('context','show') | Out-String).Trim()
    $endpoint = (Docker-Checked @('context','inspect',$context,'--format','{{.Endpoints.docker.Host}}') | Out-String).Trim()
    if ($endpoint.StartsWith('npipe://')) { $env:POD_RELEASE_SOCKET = '/var/run/docker.sock' }
    elseif ($endpoint.StartsWith('unix:///')) { $env:POD_RELEASE_SOCKET = $endpoint.Substring(7) }
    else { throw 'Only local Docker Desktop/Unix contexts are supported. Select a local context.' }
    if ((Docker-Checked @('--context',$context,'info','--format','{{.OSType}}') | Out-String).Trim() -ne 'linux') { throw 'Select Linux containers in Docker Desktop.' }
    Docker-Checked @('--context',$context,'compose','version') | Out-Null
    $state = Join-Path $PSScriptRoot '.classroom-project'
    if (-not (Test-Path -LiteralPath $state)) {
        if ($Action -ne 'start') { throw 'No saved classroom project.' }
        $newId = 'pod-public-' + [guid]::NewGuid().ToString('N')
        $stream = [System.IO.File]::Open($state, [System.IO.FileMode]::CreateNew)
        try { $bytes = [System.Text.Encoding]::ASCII.GetBytes($newId + "`n"); $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
    }
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
        # Remove inherited ACLs before writing any teacher secret.
        [System.IO.File]::WriteAllText($log, '')
        $acl = New-Object System.Security.AccessControl.FileSecurity
        $acl.SetAccessRuleProtection($true,$false)
        $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
        $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($user,'FullControl','Allow')))
        Set-Acl -LiteralPath $log -AclObject $acl
        Docker-Checked ($common + @('logs','--no-color','classroom')) | Set-Content -LiteralPath $log
        Write-Host 'Teacher: http://localhost:8765/teacher'
        Write-Host 'Projector: http://localhost:8765/projector'
        Write-Host 'Keep teacher-private.log private: it contains the teacher key.'
    }
} catch { Write-Error $_; exit 1 }
