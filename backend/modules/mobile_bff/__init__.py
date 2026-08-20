"""Mobile backend-for-frontend.

Serves the Flutter client at `/api/mobile/v1`. Composes the existing services
rather than duplicating their SQL, so the web console and Electron desktop app
keep using the routers they already use, unchanged.
"""
