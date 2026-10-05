"""HO backend self-update + fleet status.

Lets a super-admin see each HO node's running code version and trigger a remote
`git pull origin main` + dependency reinstall + backend restart from the HO UI,
instead of RDP-ing into every box. The node that serves the UI orchestrates its
peers (listed in the bootstrap ho_routes registry) server-side, so the browser
never has to make cross-origin calls to each box.
"""
