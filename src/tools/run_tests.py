"""
Wrapper de compatibilidade — use preferencialmente: invoke test
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = ["invoke", "test"]
    if args:
        cmd += ["--args", " ".join(args)]
    result = subprocess.run(cmd, cwd=str(ROOT))
    sys.exit(result.returncode)
