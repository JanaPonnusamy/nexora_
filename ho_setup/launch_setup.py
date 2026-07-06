"""PyInstaller entry point for HO_Setup.exe (the wizard)."""
import os
import sys

# Allow running as a loose script (the frozen exe sets package context already).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ho_setup.wizard import main

if __name__ == "__main__":
    main()
