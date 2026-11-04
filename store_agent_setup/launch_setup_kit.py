"""PyInstaller entry point for NexoraSetup.exe (the one Nexora install kit)."""
import os
import sys

# Allow running as a loose script (frozen exe sets the package context already).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from store_agent_setup.setup_kit.app import main

if __name__ == "__main__":
    main(sys.argv[1:])
