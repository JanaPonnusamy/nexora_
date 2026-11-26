"""Nexora Setup -- one small kit for every Nexora install (owner directive 2026-11-04).

The kit carries NO app exes. It reads this PC's spec, signs in to HO once,
binds the PC to a store (a super admin picks which), downloads the Device
Controller from HO, enrolls it, seals the Store Agent's identity, and asks HO
to install the ticked apps. HO turns that into signed controller ``install``
commands, so the controller is the one engine that installs, updates and
watches every app on the PC from then on.
"""

KIT_VERSION = "1.0.0"
EXE_NAME = "NexoraSetup.exe"

# Offered in the HO box (the operator can type any other URL).
KNOWN_HO_URLS = (
    ("http://122.252.246.181:8444", "Success / SMS HO - internet"),
    ("http://192.168.10.32:8000", "Success / SMS HO - LAN"),
    ("http://122.252.246.181:8445", "Main HO - internet"),
    ("http://192.168.10.73:8000", "Main HO - LAN"),
)
