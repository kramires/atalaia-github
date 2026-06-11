#!/usr/bin/env python3
"""Wrapper CLI — implementação em src/dashboard/generator.py (SPEC-12 §7)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # raiz do projeto no path

from src.dashboard.generator import main

if __name__ == "__main__":
    main()
