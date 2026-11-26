"""Send a WhatsApp alert using the same profile/phone the sync health monitor uses.

    echo text | backend\\.venv\\Scripts\\python.exe ops\\ho_watch\\send_alert.py
Exit 0 only when WhatsApp reports "sent".
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from modules.sync import health_monitor  # noqa: E402  (reuses its profile/phone lookup)
from modules.whatsapp import service as wa  # noqa: E402


def main():
    text = sys.stdin.read().strip()
    if not text:
        return 2
    profile_id, phone = health_monitor._alert_phone()
    if not profile_id or not phone:
        print("no WhatsApp profile/phone configured", file=sys.stderr)
        return 3
    result = wa.send_message(profile_id, phone, text[:3500])
    print(result)
    return 0 if (result or {}).get("status") == "sent" else 1


if __name__ == "__main__":
    sys.exit(main())
