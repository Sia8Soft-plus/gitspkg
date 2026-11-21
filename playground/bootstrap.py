"""Prepare an isolated, credential-free copy of the CLI for the demo."""

import json
from pathlib import Path
import shutil
import sys
import zipfile


REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".playground"


def prepare_package(remote):
    source = REPO / "playground" / "packages" / "demo-math"
    members = {
        "demo-math/" + path.relative_to(source).as_posix(): path.read_bytes()
        for path in sorted(source.rglob("*")) if path.is_file()
    }
    archive = remote / "GCC" / "demo-math" / "stable" / "demo-math@1.0.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    # Keep timestamps stable on repeat setup, but refresh edited package sources.
    if archive.exists():
        with zipfile.ZipFile(archive) as bundle:
            if set(bundle.namelist()) == set(members) and all(
                    bundle.read(name) == content for name, content in members.items()):
                return
    temporary = archive.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, content in members.items():
            bundle.writestr(name, content)
    temporary.replace(archive)


def main():
    runtime = STATE / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    for name in ("gits", "utils"):
        shutil.copytree(REPO / name, runtime / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(REPO / "main.py", runtime / "main.py")
    (runtime / "utils" / "generate_config.py").write_text(
        'def gene_conf(parent_dir):\n'
        '    raise RuntimeError("System installation is disabled in the demo")\n',
        encoding="utf-8")
    conf = runtime / "conf"
    conf.mkdir(exist_ok=True)
    (conf / "__init__.py").write_text("", encoding="utf-8")
    (conf / "config.py").write_text(
        'VERSION = "playground"\nPUBLISH_DATE = "demo"\n'
        'OS = "demo"\npassword = "public-demo-only"\n', encoding="utf-8")
    cache = STATE / "lean"
    cache.mkdir(exist_ok=True)
    config = {"lean": {
        "lean_remote_ip": "unused.invalid", "lean_remote_port": 22,
        "lean_remote_user": "demo", "lean_remote_pwd": "unused",
        "lean_remote_path": "/date/gits/base_lean",
        "lean_local_path": str(cache),
    }, "base_url": "https://example.invalid/"}
    (conf / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    remote = STATE / "remote" / "linux-12"
    remote.mkdir(parents=True, exist_ok=True)
    (remote / "import.cmake").write_text("# Public demo: no SDK imports.\n", encoding="utf-8")
    (remote / "gits-usage-readme.md").write_text(
        "# Public demo-math package\n\nHeader-only C++ addition example; no model inference.\n", encoding="utf-8")
    prepare_package(remote)

    project = STATE / "project"
    project.mkdir(exist_ok=True)
    for item in (REPO / "playground" / "fixtures").iterdir():
        shutil.copy2(item, project / item.name)
    bin_dir = STATE / "bin"
    bin_dir.mkdir(exist_ok=True)
    launcher = bin_dir / "gis"
    launcher.write_text(
        f'#!{sys.executable}\nimport runpy\n'
        f'runpy.run_path({str(REPO / "playground" / "run.py")!r}, run_name="__main__")\n',
        encoding="utf-8")
    launcher.chmod(0o755)
    print(f"Prepared isolated playground: {project}")
    print("Try building before gis update: the missing demo_math.hpp error is expected.")
    print(f"Run: {sys.executable} {REPO / 'playground' / 'run.py'} status --lean -m setup.manifest")


if __name__ == "__main__":
    main()
