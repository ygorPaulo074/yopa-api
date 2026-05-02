"""
Executa os testes da aplicação e aciona clear_data.py ao final.
Uso: python src/tools/run_tests.py [pytest_args...]
"""
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    # Garante .initialized para evitar setup interativo durante os testes
    flag = ROOT / ".initialized"
    flag_created = not flag.exists()
    if flag_created:
        flag.write_text("test run")

    try:
        args = ["python", "-m", "pytest", "src/tests/", "-v", "--tb=short"] + sys.argv[1:]
        result = subprocess.run(args, cwd=str(ROOT))
    finally:
        if flag_created and flag.exists():
            flag.unlink()

        # Limpa dados gerados apenas em runs sem argumento explícito de path
        subprocess.run(["python", "src/tools/clear_data.py"], cwd=str(ROOT))

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
