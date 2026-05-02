"""
Limpa todos os dados gerados durante a execução (apenas ambiente de desenvolvimento).
Uso: python src/tools/clear_data.py [--path ./data]
"""
import sys
import shutil
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def clear_local_data(data_path: Path) -> None:
    if not data_path.exists():
        print(f"[clear_data] Path not found, skipping: {data_path}")
        return
    try:
        shutil.rmtree(data_path)
        data_path.mkdir(parents=True)
        print(f"[clear_data] Cleared: {data_path}")
    except Exception as e:
        print(f"[clear_data] Error: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Clear local storage data")
    parser.add_argument("--path", default=None, help="Path to data directory (default: from .env or ./data)")
    args = parser.parse_args()

    if args.path:
        data_path = Path(args.path)
    else:
        # Try to read from .env
        env_file = ROOT / ".env"
        data_path = ROOT / "data"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("DATA_PATH="):
                    val = line.split("=", 1)[1].strip()
                    if val:
                        data_path = Path(val)
                    break

    clear_local_data(data_path)


if __name__ == "__main__":
    main()
