"""Native Windows PowerShell must not inherit incompatible Core modules."""
import os
import pytest
from scripts import classroom_backup as backup


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows PowerShell module discovery')
@pytest.mark.parametrize('operation', ['query', 'mkdir', 'privatize'])
def test_backup_uses_native_acl_module_despite_foreign_module_path(tmp_path, monkeypatch, operation):
    private = tmp_path / 'private'
    backup.private_mkdir(private)
    modules = tmp_path / 'core-only-modules'
    module = modules / 'Microsoft.PowerShell.Security'
    module.mkdir(parents=True)
    # Synthetic incompatible Core module: no code is run from this manifest.
    (module / 'Microsoft.PowerShell.Security.psd1').write_text(
        "@{RootModule='Missing.CoreOnly.dll';ModuleVersion='99.0';"
        "GUID='bbff8ad2-6bae-4a03-9b1f-b2b66b57faf2';"
        "CmdletsToExport=@('Get-Acl','Set-Acl')}", encoding='utf-8')
    monkeypatch.setenv('PSModulePath', str(modules))
    if operation == 'query':
        backup.require_private(private)
    elif operation == 'mkdir':
        backup.private_mkdir(private / 'new')
    else:
        (private / 'file').write_bytes(b'synthetic')
        backup.privatize(private)
    assert os.environ['PSModulePath'] == str(modules)
    assert private.is_dir()
