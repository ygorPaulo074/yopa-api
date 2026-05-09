"""
Wrapper de compatibilidade — use preferencialmente: invoke clear
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=None)
    args = parser.parse_args()

    cmd = ["invoke", "clear"]
    if args.path:
        cmd += ["--path", args.path]
    result = subprocess.run(cmd, cwd=str(ROOT))
    sys.exit(result.returncode)
