#!/usr/bin/env python3
"""Wrapper CLI — implementação em src/intake/ccomsex/etl_loader.py (SPEC-01 §8.3)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # raiz do projeto no path

from src.intake.ccomsex.etl_loader import main

if __name__ == "__main__":
    main()
