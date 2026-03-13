from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"


def main(argv: list[str] | None = None) -> int:
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    from asset_mapping_agent.cli import main as cli_main

    original_argv = sys.argv[:]
    try:
        sys.argv = [str(ROOT / "agent.py"), *(argv if argv is not None else sys.argv[1:])]
        return int(cli_main())
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
