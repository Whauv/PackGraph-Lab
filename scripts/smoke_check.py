from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print(f"\n> {' '.join(command)}")
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PackGraph backend/frontend smoke checks.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip unittest discovery.")
    parser.add_argument("--skip-js", action="store_true", help="Skip frontend JavaScript syntax checks.")
    args = parser.parse_args()

    run([sys.executable, "-m", "compileall", "app", "tests", "scripts"])
    if not args.skip_tests:
        run([sys.executable, "-m", "unittest", "discover", "tests"])

    if not args.skip_js:
        if not shutil.which("node"):
            print("\n! Node.js was not found, skipping frontend syntax checks.")
            return 0
        for path in [
            "web/assets/app.js",
            "web/assets/modules/chat-drawer.js",
            "web/assets/modules/graph-chat-controller.js",
            "web/assets/modules/source-intake-controller.js",
            "web/assets/modules/workbench-controller.js",
        ]:
            run(["node", "--check", path])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
