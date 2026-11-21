"""Verify the delivered C++ dependency and optionally build and run the example."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".playground"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="Also compile and run the C++ example.")
    args = parser.parse_args()
    header = (REPO / "playground/packages/demo-math/include/demo_math.hpp").read_text(encoding="utf-8")
    expected = {
        "lean/demo-math@1.0@GCC/include/demo_math.hpp": header,
        "project/workspace/include/demo_math.hpp": header,
    }
    for name, content in expected.items():
        path = STATE / name
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            raise SystemExit(f"FAIL: missing or incorrect {name}")
    if (STATE / "lean/demo-math@1.0@GCC/demo-math").exists():
        raise SystemExit("FAIL: matching package wrapper was not flattened")
    result = subprocess.run(
        [sys.executable, str(REPO / "playground/run.py"), "status", "--lean", "-m", "setup.manifest"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    print(result.stdout, flush=True)
    for marker in ("0 unresolved packages", "0 missing packages", "0 packages need to update",
                   "demo-math: copy include/* to ./workspace/include/ OK!"):
        if marker not in result.stdout:
            raise SystemExit(f"FAIL: status marker missing: {marker}")
    for marker in ("Command rejected", "Connection failed", "Error:", "Cannot check files"):
        if marker in result.stdout:
            raise SystemExit(f"FAIL: status reported {marker}")
    print("PASS: real CLI selected, extracted, flattened, copied and checked demo-math.", flush=True)
    if args.build:
        cmake = shutil.which("cmake")
        ctest = shutil.which("ctest")
        if not cmake or not ctest:
            raise SystemExit("CMake/CTest is missing. Install playground/requirements.txt first.")
        project = STATE / "project"
        for command in (
                [cmake, "-S", ".", "-B", "build"],
                [cmake, "--build", "build", "--config", "Release"],
                [ctest, "--test-dir", "build", "-C", "Release", "--output-on-failure"]):
            subprocess.run(command, cwd=project, check=True)
        print("PASS: built and ran C++ example: 2 + 3 = 5")


if __name__ == "__main__":
    main()
