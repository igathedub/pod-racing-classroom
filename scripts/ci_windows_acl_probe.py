"""Probe only fresh CI fixtures; emit booleans/error numbers, never descriptors.

This is a diagnostic, not a replacement for native backup acceptance tests.
No privileges are enabled. All mutations are confined to newly created fixtures;
DACL comparison measures Windows owner-update side effects, not an assumption.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile


METHODS = {'set_acl', 'owner_only_dotnet', 'owner_only_win32', 'owner_and_dacl_win32'}
BOOL_FIELDS = {'owner_matches', 'before_owner_matches', 'dacl_unchanged', 'owner_rights_preserved'}
NUMBER_FIELDS = {'hresult', 'native_error_code'}
PHASES = {'setup', 'seed_dacl', 'before_acl', 'owner_update', 'after_acl'}


def public_report(raw):
    if raw.get('method') not in METHODS or raw.get('result') not in {'ok', 'failed'}:
        raise ValueError('Invalid diagnostic result')
    result = {key: raw[key] for key in ('method', 'result')}
    if 'phase' in raw:
        if raw['phase'] not in PHASES:
            raise ValueError('Invalid diagnostic phase')
        result['phase'] = raw['phase']
    for key in BOOL_FIELDS | NUMBER_FIELDS:
        if key not in raw:
            continue
        expected = bool if key in BOOL_FIELDS else int
        if type(raw[key]) is not expected:
            raise ValueError('Invalid diagnostic field type')
        result[key] = raw[key]
    return result


SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$methods = @('set_acl', 'owner_only_dotnet', 'owner_only_win32', 'owner_and_dacl_win32')
$rows = @()
function Record-Failure($row, $failure, $phase) {
    $row.result = 'failed'
    $row.phase = $phase
    $row.hresult = [int]$failure.Exception.HResult
    $cause = $failure.Exception
    for ($i=0; $i -lt 4 -and $null -ne $cause; $i++) {
        if ($cause -is [System.ComponentModel.Win32Exception]) {
            $row.native_error_code = [int]$cause.NativeErrorCode
            break
        }
        $cause = $cause.InnerException
    }
}
try {
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class PodCiOwnerProbe {
    [DllImport("advapi32.dll", CharSet=CharSet.Unicode)]
    public static extern uint SetNamedSecurityInfo(string path, int objectType,
        uint information, byte[] owner, IntPtr group, IntPtr dacl, IntPtr sacl);
    [DllImport("advapi32.dll", EntryPoint="SetNamedSecurityInfoW", CharSet=CharSet.Unicode, ExactSpelling=true)]
    public static extern uint SetOwnerAndDacl(string path, int objectType,
        uint information, byte[] owner, IntPtr group, byte[] dacl, IntPtr sacl);
}
'@
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
foreach ($method in $methods) {
    $row = @{method=$method; result='failed'; owner_rights_preserved=$false; dacl_unchanged=$false}
    $phase = 'seed_dacl'
    try {
    $path = Join-Path $env:POD_CI_ACL_FIXTURE_ROOT $method
    if ($method -eq 'owner_and_dacl_win32') {
        # Seed OWNER RIGHTS on this fourth fresh fixture only, using DACL-only flags.
        $fixtureAcl = Get-Acl -LiteralPath $path
        $ownerRights = [System.Security.Principal.SecurityIdentifier]::new('S-1-3-4')
        $fixtureAcl.AddAccessRule([System.Security.AccessControl.FileSystemAccessRule]::new($ownerRights, 'ReadPermissions', 'Allow'))
        $raw = [System.Security.AccessControl.RawSecurityDescriptor]::new($fixtureAcl.GetSecurityDescriptorBinaryForm(), 0)
        $seedDacl = New-Object byte[] $raw.DiscretionaryAcl.BinaryLength
        $raw.DiscretionaryAcl.GetBinaryForm($seedDacl, 0)
        $seedCode = [PodCiOwnerProbe]::SetOwnerAndDacl($path, 1, 4, $null, [IntPtr]::Zero, $seedDacl, [IntPtr]::Zero)
        if ($seedCode -ne 0) {
            $row.native_error_code = [int]$seedCode
            throw 'Fresh fixture DACL setup failed'
        }
    }
    $phase = 'before_acl'
    $before = Get-Acl -LiteralPath $path
    $dacl = $before.GetSecurityDescriptorSddlForm([System.Security.AccessControl.AccessControlSections]::Access)
    $row.before_owner_matches = ($before.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -eq $user.Value)
    $phase = 'owner_update'
    try {
        if ($method -eq 'set_acl') {
            $before.SetOwner($user)
            Set-Acl -LiteralPath $path -AclObject $before
        } elseif ($method -eq 'owner_only_dotnet') {
            $ownerOnly = [System.IO.Directory]::GetAccessControl($path, [System.Security.AccessControl.AccessControlSections]::Owner)
            $ownerOnly.SetOwner($user)
            [System.IO.Directory]::SetAccessControl($path, $ownerOnly)
        } elseif ($method -eq 'owner_only_win32') {
            $sid = New-Object byte[] $user.BinaryLength
            $user.GetBinaryForm($sid, 0)
            # SE_FILE_OBJECT=1; OWNER_SECURITY_INFORMATION=1. No DACL/SACL flags.
            $code = [PodCiOwnerProbe]::SetNamedSecurityInfo($path, 1, 1, $sid, [IntPtr]::Zero, [IntPtr]::Zero, [IntPtr]::Zero)
            $row.native_error_code = [int]$code
            if ($code -ne 0) { throw 'Owner-only operation failed' }
        } else {
            $sid = New-Object byte[] $user.BinaryLength
            $user.GetBinaryForm($sid, 0)
            $raw = [System.Security.AccessControl.RawSecurityDescriptor]::new($before.GetSecurityDescriptorBinaryForm(), 0)
            $originalDacl = New-Object byte[] $raw.DiscretionaryAcl.BinaryLength
            $raw.DiscretionaryAcl.GetBinaryForm($originalDacl, 0)
            # OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION = 5; no group/SACL.
            $code = [PodCiOwnerProbe]::SetOwnerAndDacl($path, 1, 5, $sid, [IntPtr]::Zero, $originalDacl, [IntPtr]::Zero)
            $row.native_error_code = [int]$code
            if ($code -ne 0) { throw 'Owner-and-DACL operation failed' }
        }
        $row.result = 'ok'
    } catch {
        Record-Failure $row $_ $phase
    }
    $phase = 'after_acl'
    $after = Get-Acl -LiteralPath $path
    $row.owner_matches = ($after.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -eq $user.Value)
    $row.owner_rights_preserved = @($after.Access | Where-Object { $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value -eq 'S-1-3-4' }).Count -gt 0
    $row.dacl_unchanged = ($dacl -eq $after.GetSecurityDescriptorSddlForm([System.Security.AccessControl.AccessControlSections]::Access))
    } catch {
        Record-Failure $row $_ $phase
    }
    $rows += $row
}
} catch {
    $failure = $_
    $rows = @()
    foreach ($method in $methods) {
        $row = @{method=$method; result='failed'; owner_rights_preserved=$false; dacl_unchanged=$false}
        Record-Failure $row $failure 'setup'
        $rows += $row
    }
}
ConvertTo-Json -InputObject $rows -Compress
'''


def main():
    if os.name != 'nt':
        raise SystemExit('Windows-only diagnostic')
    try:
        base = os.environ.get('RUNNER_TEMP') if os.environ.get('GITHUB_ACTIONS') == 'true' else os.environ.get('TMPDIR')
        if not base or not Path(base).is_dir():
            raise SystemExit('An explicit CI/scratch temporary root is required')
        with tempfile.TemporaryDirectory(prefix='pod-ci-acl-', dir=base) as temporary:
            root = Path(temporary)
            for method in METHODS:
                (root / method).mkdir(mode=0o700)
            result = subprocess.run(
                ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', SCRIPT],
                env={**{k: v for k, v in os.environ.items()
                        if k.casefold() != "psmodulepath"},
                     "POD_CI_ACL_FIXTURE_ROOT": str(root)},
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode:
                raise SystemExit('Isolated ACL diagnostic failed; raw diagnostics suppressed') from None
            try:
                reports = [public_report(row) for row in json.loads(result.stdout)]
                if {row['method'] for row in reports} != METHODS or len(reports) != len(METHODS):
                    raise ValueError('Incomplete diagnostic')
            except (ValueError, TypeError, KeyError):
                raise SystemExit('Invalid ACL diagnostic; raw output suppressed') from None
        print(json.dumps(reports, sort_keys=True))
    except Exception:
        # Includes fixture creation, process startup/timeouts and context cleanup.
        raise SystemExit('Isolated ACL diagnostic failed; raw diagnostics suppressed') from None
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
