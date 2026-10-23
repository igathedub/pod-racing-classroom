"""CI-only policy regression tests; no host security configuration is performed."""
import copy
import importlib.util
import io
from pathlib import Path, PurePosixPath
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


SCRIPT = Path(__file__).with_name("chromium_apparmor.py")
SPEC = importlib.util.spec_from_file_location("chromium_apparmor", SCRIPT)
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)
METADATA = {"browsers": [
    {"name": "chromium", "revision": "123"},
    {"name": "chromium-headless-shell", "revision": "123"},
]}


class PolicyTests(unittest.TestCase):
    def test_exact_profiles_cover_browser_and_default_headless_shell(self):
        root = PurePosixPath("/home/runner/work/_temp/pod-ci-playwright")
        paths = [root / "chromium-123/chrome-linux64/chrome",
                 root / "chromium_headless_shell-123/chrome-headless-shell-linux64/chrome-headless-shell"]
        rendered = policy.render_policy(paths)
        for path in paths:
            self.assertIn(f'"{path.as_posix()}" flags=(unconfined)', rendered)
        self.assertEqual(rendered.count("  userns,"), 2)
        self.assertNotIn("*", rendered)
        self.assertNotIn("@{", rendered)


    def test_rejects_policy_injection_and_relative_paths(self):
        for value in ('/tmp/*/chrome', '/tmp/@{HOME}/chrome', '/tmp/{a,b}/chrome',
                      '/tmp/"/chrome', '/tmp/white space/chrome', 'relative/chrome',
                      '/tmp/../chrome', '/tmp/\nchrome'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                policy.render_policy([PurePosixPath(value)])

    def installation(self, root, legacy=False):
        layouts = ('chrome-linux/chrome', 'chrome-linux/headless_shell') if legacy else (
            'chrome-linux64/chrome', 'chrome-headless-shell-linux64/chrome-headless-shell')
        paths = []
        for entry, layout in zip(METADATA['browsers'], layouts):
            path = root / f"{entry['name'].replace('-', '_')}-123" / layout
            path.parent.mkdir(parents=True)
            path.write_bytes(b'\x7fELFfixture')
            paths.append(path)
        return paths

    def test_discovers_both_executables_from_metadata_in_known_layouts(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                paths = self.installation(root, legacy)
                self.assertEqual(policy.discover_executables(root, METADATA), paths)

    def test_missing_headless_shell_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.installation(root)
            paths[1].unlink()
            with self.assertRaisesRegex(ValueError, 'Unknown or ambiguous'):
                policy.discover_executables(root, METADATA)

    def test_unknown_or_ambiguous_layout_fails_closed(self):
        for ambiguous in (False, True):
            with self.subTest(ambiguous=ambiguous), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                paths = self.installation(root)
                other = paths[0].parents[1] / ('chrome-linux/chrome' if ambiguous else 'unknown/chrome')
                other.parent.mkdir()
                other.write_bytes(b'\x7fELFfixture')
                if not ambiguous:
                    paths[0].unlink()
                with self.assertRaisesRegex(ValueError, 'Unknown or ambiguous'):
                    policy.discover_executables(root, METADATA)

    def test_descriptor_drift_fails_closed(self):
        for mutation in ('missing', 'duplicate', 'revision', 'override'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.installation(root)
                metadata = copy.deepcopy(METADATA)
                if mutation == 'missing':
                    metadata['browsers'].pop()
                elif mutation == 'duplicate':
                    metadata['browsers'].append(metadata['browsers'][1])
                elif mutation == 'revision':
                    metadata['browsers'][0]['revision'] = '../escape'
                else:
                    metadata['browsers'][0]['revisionOverrides'] = {'ubuntu26.04-x64': '999'}
                with self.assertRaises(ValueError):
                    policy.discover_executables(root, metadata)

    def test_symlink_executable_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.installation(root)
            target = root / 'replacement'
            paths[1].rename(target)
            try:
                paths[1].symlink_to(target)
            except OSError:
                self.skipTest('Symlink creation unavailable on this host')
            with self.assertRaisesRegex(ValueError, 'Symlink'):
                policy.discover_executables(root, METADATA)

    def test_guard_requires_hosted_linux_and_dedicated_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
                   'RUNNER_OS': 'Linux', 'RUNNER_TEMP': directory,
                   'PLAYWRIGHT_BROWSERS_PATH': str(Path(directory) / 'pod-ci-playwright')}
            self.assertEqual(policy.require_hosted_linux(env, 'linux'), Path(env['PLAYWRIGHT_BROWSERS_PATH']))
            for key, value in (('GITHUB_ACTIONS', ''), ('RUNNER_ENVIRONMENT', 'self-hosted'),
                               ('RUNNER_OS', 'Windows'), ('PLAYWRIGHT_BROWSERS_PATH', directory)):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    policy.require_hosted_linux({**env, key: value}, 'linux')
            for platform in ('win32', 'darwin'):
                with self.subTest(platform=platform), self.assertRaises(ValueError):
                    policy.require_hosted_linux(env, platform)

    def test_linux_validation_checks_elf_executable_owner_and_permissions(self):
        # Mock only Linux-specific filesystem metadata; never invoke security tools.
        for failure in (None, 'execute', 'elf', 'owner', 'group-write', 'other-write'):
            with self.subTest(failure=failure):
                executable = MagicMock()
                executable.parents = ()
                executable.open.return_value = io.BytesIO(b'nope' if failure == 'elf' else b'\x7fELF')
                executable.lstat.return_value = SimpleNamespace(
                    st_uid=999 if failure == 'owner' else 1001,
                    st_mode={'group-write': 0o775, 'other-write': 0o757}.get(failure, 0o755))
                with patch.object(policy.os, 'access', return_value=failure != 'execute'), \
                        patch.object(policy.os, 'getuid', return_value=1001, create=True):
                    if failure is None:
                        policy.verify_linux_installation(executable, [executable])
                    else:
                        with self.assertRaises(ValueError):
                            policy.verify_linux_installation(executable, [executable])


if __name__ == "__main__":
    unittest.main()
