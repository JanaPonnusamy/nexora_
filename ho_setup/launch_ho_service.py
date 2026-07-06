"""PyInstaller entry point for HO_Backend.exe (the Windows service host)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ho_setup.ho_service import main

if __name__ == "__main__":
    main()
