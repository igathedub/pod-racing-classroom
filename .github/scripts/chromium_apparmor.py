"""Generate an exact-path AppArmor userns allowance, only on hosted Linux CI.

Implements Chromium's documented per-executable AppArmor option, NOT a global
sysctl change or a Chromium sandbox bypass:
https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md

Playwright's installed browsers.json selects the revisions. Only known Linux
executable layouts within our dedicated, freshly installed runner-temp cache are
accepted. An unknown revision override/layout fails closed. This script never
loads policy or invokes sudo; ci.yml installs the generated file on the runner.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys


LAYOUTS = {
    "chromium": ("chrome-linux64/chrome", "chrome-linux/chrome"),
    "chromium-headless-shell": (
        "chrome-headless-shell-linux64/chrome-headless-shell",
        "chrome-linux/headless_shell",
    ),
}


def render_policy(executables):
    profiles = ["# Generated for exact Playwright executables on an ephemeral CI runner.\n"]
    for index, executable in enumerate(executables):
        path = executable.as_posix()
        # Reject AppArmor glob/variable/quote injection rather than escaping it.
        if not re.fullmatch(r"/[A-Za-z0-9_./-]+", path) or ".." in path.split("/"):
            raise ValueError(f"Unsafe AppArmor attachment path: {path!r}")
        profiles.append(
            f'profile pod-ci-playwright-{index} "{path}" flags=(unconfined) {{\n'
            "  userns,\n"
            "}\n"
        )
    return "\n".join(profiles)


def discover_executables(cache, metadata):
    result = []
    for name, layouts in LAYOUTS.items():
        entries = [entry for entry in metadata["browsers"] if entry["name"] == name]
        if len(entries) != 1:
            raise ValueError(f"Expected exactly one Playwright descriptor for {name}")
        entry = entries[0]
        revision = entry["revision"]
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9]+", revision):
            raise ValueError(f"Unknown revision for {name}")
        if entry.get("revisionOverrides"):
            raise ValueError(f"Review platform revision overrides for {name} before granting userns")
        directory = cache / f"{name.replace('-', '_')}-{revision}"
        candidates = [directory / layout for layout in layouts if (directory / layout).is_file()]
        if len(candidates) != 1:
            raise ValueError(f"Unknown or ambiguous executable layout for {name}: {directory}")
        executable = candidates[0]
        # Reject even in-cache symlinks: the policy must attach to the real binary.
        for path in (executable, *executable.parents):
            if path.is_symlink():
                raise ValueError(f"Symlink in browser installation: {path}")
            if path == cache:
                break
        if not executable.resolve().is_relative_to(cache.resolve()):
            raise ValueError(f"Browser executable escapes dedicated cache: {executable}")
        result.append(executable)
    return result


def verify_linux_installation(cache, executables):
    """Do not grant userns to an installation writable by another runner user."""
    for executable in executables:
        if not os.access(executable, os.X_OK):
            raise ValueError(f"Browser is not executable: {executable}")
        with executable.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                raise ValueError(f"Browser is not a Linux ELF executable: {executable}")
        for path in (executable, *executable.parents):
            info = path.lstat()
            if info.st_uid != os.getuid() or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise ValueError(f"Unexpected browser ownership/permissions: {path}")
            if path == cache:
                break


def require_hosted_linux(environ, platform):
    if (platform != "linux" or environ.get("GITHUB_ACTIONS") != "true"
            or environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or environ.get("RUNNER_OS") != "Linux"):
        raise ValueError("Policy generation is restricted to ephemeral GitHub-hosted Linux runners")
    temporary = Path(environ["RUNNER_TEMP"])
    expected = temporary / "pod-ci-playwright"
    if environ.get("PLAYWRIGHT_BROWSERS_PATH") != str(expected):
        raise ValueError("Expected the dedicated runner-temp Playwright cache")
    if temporary.is_symlink() or expected.is_symlink():
        raise ValueError("Runner temporary/cache directory must not be a symlink")
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cache = require_hosted_linux(os.environ, sys.platform).resolve(strict=True)
    import playwright

    metadata_path = Path(playwright.__file__).parent / "driver/package/browsers.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    executables = discover_executables(cache, metadata)
    verify_linux_installation(cache, executables)
    policy = render_policy(executables)
    args.output.write_text(policy, encoding="utf-8")
    print(policy, end="")


if __name__ == "__main__":
    main()
