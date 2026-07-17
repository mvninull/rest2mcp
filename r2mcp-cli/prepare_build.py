"""Script para preparar o package r2mcp-cli para publicacao no PyPI.
Copia o source do CLI do diretorio raiz para dentro de r2mcp-cli/.

Uso:
    cd r2mcp-cli
    python prepare_build.py
    python -m build
    twine upload dist/*
"""

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CLI_SRC = ROOT / "r2mcp_cli"
DEST = HERE / "r2mcp_cli"


def main():
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(CLI_SRC, DEST, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"Copiado: {CLI_SRC} -> {DEST}")
    print("Pronto para buildar. Execute: python -m build")


if __name__ == "__main__":
    main()
