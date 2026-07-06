"""PyInstaller entry point for HO_Uninstall.exe (the uninstaller)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ho_setup.uninstaller import main

if __name__ == "__main__":
    main()
