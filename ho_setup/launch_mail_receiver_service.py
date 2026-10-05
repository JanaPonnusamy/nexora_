"""PyInstaller entry point for NexoraHOMailReceiver.exe (the Windows service host)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ho_setup.mail_receiver_service import main

if __name__ == "__main__":
    main()
