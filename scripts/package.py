"""Package application source, excluding databases, secrets and virtualenvs."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {"arena", "web", "sandbox", "examples", "scripts", "tests"}
FILES = {"README.md", "README.de.md", "LICENSE", "SPEC.md", "pyproject.toml", "uv.lock", "launch.py", "Setup.cmd", "Start-classroom.cmd", "Docker-start.cmd", "Docker-start.sh", "Dockerfile", "compose.yaml", ".dockerignore", ".gitattributes", ".gitignore", "VERIFICATION.md"}


def main() -> None:
    output = ROOT / "artifacts" / "Pod-Racing-Classroom.zip"
    output.parent.mkdir(exist_ok=True)
    count = 0
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if any(part in {".venv", ".git", "data", "artifacts", "__pycache__", ".pytest_cache", ".ruff_cache"} for part in relative.parts):
                continue
            if relative.parts[0] not in DIRECTORIES and str(relative) not in FILES:
                continue
            archive.write(path, Path("Pod-Racing-Classroom") / relative)
            count += 1
    print(f"Created {output} with {count} source files; no classroom data or secrets included.")


if __name__ == "__main__":
    main()
