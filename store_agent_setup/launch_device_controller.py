"""PyInstaller entry point for NexoraDeviceController.exe (service + setup CLI)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from store_agent_setup.device_controller.service import main

if __name__ == "__main__":
    main()
