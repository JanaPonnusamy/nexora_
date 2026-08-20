# Nexora Supplier Stock — desktop deployment

One standalone Electron app. It has three role-gated screens plus Settings, and
the nav shows only what the signed-in user's role allows:

| Screen | Visible to |
|---|---|
| **Stock Check** (Stock Availability) | everyone signed in |
| **Supplier Stock Analysis** | admin-tier only — hidden for purchase-only and salesman-only logins |
| **NMW Bill Details** (NMW Sales Report) | everyone (server scopes store users to their own approved bills) |
| **Settings** | everyone |

Visibility is enforced both in the nav ([src/App.jsx](src/App.jsx) `navItems`) and
server-side (the API 403s / scopes results), so the client never has to be trusted.

Data comes from the **central HO backend** over HTTP; the API URL is set per PC in
the in-app **Settings** screen (default `http://localhost:8000`).

---

## 1. Build the installer (build machine with Node 18+)

```
cd desktop/supplier-stock-client
npm install
npm run dist     # -> release/Nexora-Supplier-Stock-Setup-<version>.exe
```

`electron-builder` produces an NSIS installer under `release/`. Code signing is
disabled (`build.win.signAndEditExecutable: false`) so no winCodeSign toolchain is
needed; first run downloads the NSIS helper once.

### If the installer step fails with `rename ... Access is denied` / `elevate.exe ENOENT`

On machines where antivirus (e.g. Windows Defender real-time protection) locks the
freshly-extracted NSIS stub executables, electron-builder can't rename its download
into place. Pre-seed the cache manually so it skips the download+rename, then build
against that cache:

```
SZ="node_modules/7zip-bin/win/x64/7za.exe"
CACHE=".eb-cache/nsis"; mkdir -p "$CACHE"
curl -sL -o "$CACHE/nsis.7z" https://github.com/electron-userland/electron-builder-binaries/releases/download/nsis-3.0.4.1/nsis-3.0.4.1.7z
curl -sL -o "$CACHE/res.7z"  https://github.com/electron-userland/electron-builder-binaries/releases/download/nsis-resources-3.4.1/nsis-resources-3.4.1.7z
"$SZ" x -y "$CACHE/nsis.7z" -o"$CACHE/nsis-3.0.4.1"
"$SZ" x -y "$CACHE/res.7z"  -o"$CACHE/nsis-resources-3.4.1"
ELECTRON_BUILDER_CACHE="$PWD/.eb-cache" npm run dist
```

Alternatively, enable Windows **Developer Mode** (Settings → For developers) or run
the shell as Administrator, which grants the symlink privilege electron-builder needs.

### No installer? Ship the portable folder instead

`release/win-unpacked/` is a complete, runnable app (`Nexora Supplier Stock.exe`).
Zip that folder, copy it to the PC, and run the exe directly — no installer needed.

## 2. Install on a store / HO PC

1. Copy `Nexora-Supplier-Stock-Setup-<version>.exe` to the PC and run it
   (per-user install, no admin needed; pick the install folder if prompted).
2. Launch **Nexora Supplier Stock** from the Start Menu / desktop shortcut.
3. First run only — open **Settings** and set:
   - **API base URL** → the HO server, e.g. `http://<HO-SERVER-IP>:8000`.
   - Click **Test connection** — expect "Connected successfully".
   - **Tenant ID / Store ID / Store Name** for this store (or use device
     activation → HO approves the device, which fills these in).
4. Sign in with Nexora credentials. The nav shows only the screens this login's
   role is allowed to see.

Settings persist on that PC, so steps 3–4 are one-time per machine.

## 3. Networking checklist (central HO model)

- HO backend must listen on `0.0.0.0:8000` (not just localhost) and its firewall
  must allow inbound 8000 from the store network.
- Store PCs must be able to reach the HO IP/host (same LAN, VPN, or a routed/static
  IP — see the HO multi-URL setup for failover routes).
- The app's CSP permits http/https/ws to any host, so any reachable HO URL works
  without a rebuild. Prefer HTTPS if HO is exposed beyond a trusted LAN.

## 4. Updating a deployed PC

Rebuild the installer with a bumped `version` in `package.json` and re-run it on the
PC (NSIS upgrades in place). No auto-update server is configured yet. No app icon is
set (default Electron icon) — wire `build.win.icon` when a Nexora `.ico` exists.

## Local dev

```
npm run dev             # vite + electron with hot reload + devtools
start-desktop-client.bat  # starts the backend if needed, then the dev client
```
