"""PyInstaller entry point for NexoraStoreAgentSetup.exe."""
import os
import sys

# Allow running as a loose script (frozen exe sets the package context already).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from store_agent_setup.wizard import main

if __name__ == "__main__":
    main()
