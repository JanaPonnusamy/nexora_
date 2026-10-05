"""PyInstaller entry point for NexoraStockClientWatchdog.exe (the Windows service)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from store_agent_setup.stock_client_watchdog_service import main

if __name__ == "__main__":
    main()
