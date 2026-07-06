"""PyInstaller entry point for HO_Deploy.exe (the headless deployment helper)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ho_setup.cli import main

if __name__ == "__main__":
    sys.exit(main())
