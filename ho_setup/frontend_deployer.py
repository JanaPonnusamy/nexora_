"""Frontend deployment (wizard STEP 9).

Copies the production SPA build into ``<install>\\frontend`` and configures the
API endpoint WITHOUT a rebuild: it writes ``config.js`` (which sets
``window.__UNINEX_API_BASE__``) and injects a ``<script src="/config.js">`` tag
into ``index.html``. apiClient.ts prefers that runtime value over the build-time
default, so the same bundle works against any HO server.

The backend service serves this folder (UNINEX_FRONTEND_DIR), so the SPA and the
API share one origin and one port.
"""
import shutil
from pathlib import Path

from .paths import repo_root, resource_root

_CONFIG_SCRIPT = '<script src="/config.js"></script>'


class FrontendDeployer:
    def __init__(self, config, log=None):
        self.cfg = config
        self.dest = Path(config.install_path) / "frontend"
        self._log = log or (lambda msg: None)

    def log(self, msg):
        self._log(msg)

    def _locate_frontend_build(self):
        candidates = [
            resource_root() / "frontend_dist",        # bundled in HO_Setup.exe
            repo_root() / "frontend" / "dist",        # local build (dev)
        ]
        for candidate in candidates:
            if (candidate / "index.html").is_file():
                return candidate
        return None

    def deploy(self):
        """Copy the SPA build into the install folder and configure it. Used by
        the standalone wizard (file copy + configure in one step)."""
        build = self._locate_frontend_build()
        if build is None:
            raise FileNotFoundError(
                "Frontend build not found. Run `npm run build` in frontend/ "
                "(produces frontend/dist) before building HO_Setup."
            )
        if self.dest.exists():
            shutil.rmtree(self.dest)
        shutil.copytree(build, self.dest)
        self.log(f"deployed frontend from {build}")
        self.configure()

    def configure(self):
        """Point an already-deployed SPA at the API (used by the Inno flow,
        where Inno has already copied the frontend files)."""
        if not (self.dest / "index.html").is_file():
            raise FileNotFoundError(
                f"Frontend not found at {self.dest}; nothing to configure."
            )
        self.write_runtime_config()
        self.inject_config_script()

    def write_runtime_config(self):
        path = self.dest / "config.js"
        path.write_text(self.cfg.config_js(), encoding="utf-8")
        self.log(f"wrote {path} (API base {self.cfg.api_url})")

    def inject_config_script(self):
        index = self.dest / "index.html"
        html = index.read_text(encoding="utf-8")
        if _CONFIG_SCRIPT in html:
            return
        if "</head>" in html:
            html = html.replace("</head>", f"    {_CONFIG_SCRIPT}\n  </head>", 1)
        else:  # no <head>: prepend so it loads before the app bundle
            html = _CONFIG_SCRIPT + "\n" + html
        index.write_text(html, encoding="utf-8")
        self.log("injected /config.js into index.html")
