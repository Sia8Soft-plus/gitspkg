"""Test a fresh C++ demo: missing header -> gis update -> build and run -> cache hit."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


REPO = Path(__file__).resolve().parents[1]


def run(command, cwd):
    result = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"), timeout=120)
    print("$ " + " ".join(map(str, command)), flush=True)
    print(result.stdout + result.stderr, flush=True)
    return result


def require(result, marker=None):
    if result.returncode:
        raise SystemExit(f"FAIL: command exited with {result.returncode}")
    if marker and marker not in result.stdout:
        raise SystemExit(f"FAIL: expected {marker!r}")


def main():
    cmake = shutil.which("cmake")
    if not cmake:
        raise SystemExit("Install playground/requirements.txt to provide CMake first.")
    state = REPO / ".playground"
    state.mkdir(exist_ok=True)
    state.resolve().relative_to(REPO.resolve())
    # Temporary copies keep the user's downloaded packages and edited project intact.
    with tempfile.TemporaryDirectory(prefix="cpp-check-", dir=state) as directory:
        sandbox = Path(directory)
        sandbox.resolve().relative_to(state.resolve())
        shutil.copy2(REPO / "main.py", sandbox / "main.py")
        for name in ("gits", "utils", "playground"):
            shutil.copytree(
                REPO / name, sandbox / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "generate_config.py"))
        (sandbox / "utils/generate_config.py").write_text(
            'def gene_conf(parent_dir):\n    raise RuntimeError("Use the demo bootstrap")\n',
            encoding="utf-8")
        python = sys.executable
        require(run([python, "playground/bootstrap.py"], sandbox))
        project = sandbox / ".playground/project"
        header = project / "workspace/include/demo_math.hpp"
        if header.exists():
            raise SystemExit("FAIL: bootstrap must leave the project dependency missing")
        require(run([python, "playground/run.py", "status", "--lean", "-m", "setup.manifest"],
                    sandbox), "1 missing packages")
        require(run([cmake, "-S", ".", "-B", "build"], project))
        missing = run([cmake, "--build", "build", "--config", "Release"], project)
        if not missing.returncode or "demo_math.hpp" not in missing.stdout + missing.stderr:
            raise SystemExit("FAIL: the initial build must fail specifically on demo_math.hpp")
        print("PASS: initial build failed because the dependency header is missing.", flush=True)
        update = [python, "playground/run.py", "update", "--lean", "-m", "setup.manifest", "--no-obj"]
        require(run(update, sandbox), "Succeed packages num: 1")
        require(run([python, "playground/verify.py", "--build"], sandbox),
                "PASS: built and ran C++ example: 2 + 3 = 5")
        archive = sandbox / ".playground/remote/linux-12/GCC/demo-math/stable/demo-math@1.0.zip"
        timestamp = archive.stat().st_mtime_ns
        require(run([python, "playground/bootstrap.py"], sandbox))
        if archive.stat().st_mtime_ns != timestamp:
            raise SystemExit("FAIL: repeated setup changed an unchanged package archive")
        require(run(update, sandbox), "Total lean packages num: 0")
        require(run([python, "playground/verify.py"], sandbox))
        print("PASS: missing dependency -> real gis update -> C++ build/run -> cache reuse.")


if __name__ == "__main__":
    main()
