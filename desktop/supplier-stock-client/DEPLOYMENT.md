# Nexora desktop client — deployment

One codebase, two products built from it:

| Product | Launch | Screens | Intended PC |
|---|---|---|---|
| **Nexora Stock Check** | `--stock-only` / baked `nexoraMode: "stock"` | Stock Availability + Settings | store counter PCs |
| **Nexora Supplier Stock** | default | Stock Availability, Supplier Stock Analysis, NMW Sales Report, Settings | HO / admin PC |

Both talk to the **central HO backend** over HTTP; the API URL is set per PC in the
in-app **Settings** screen (default `http://localhost:8000`). Server-side role
scoping still governs who can see Analysis / NMW export regardless of build.

---

## 1. Build the installers (on a build machine with Node 18+)

```
cd desktop/supplier-stock-client
npm install
npm run dist:stock     # -> release/Nexora-Stock-Check-Setup-<version>.exe   (store PCs)
npm run dist:full      # -> release/Nexora-Supplier-Stock-Setup-<version>.exe (HO PC)
```

`electron-builder` produces an NSIS installer under `release/`. First run downloads
NSIS helpers, so it needs internet once. Code signing is disabled
(`build.win.signAndEditExecutable: false`) so no winCodeSign toolchain is needed.

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
ELECTRON_BUILDER_CACHE="$PWD/.eb-cache" npm run dist:stock
```

Alternatively, enable Windows **Developer Mode** (Settings → For developers) or run
the shell as Administrator, which grants the symlink privilege electron-builder needs.

### No installer? Ship the portable folder instead

`release/win-unpacked/` is a complete, runnable app (`Nexora Stock Check.exe`). Zip
that folder, copy it to the store PC, and run the exe directly — no installer needed.
It carries the same baked stock-only mode.

## 2. Install on a store PC

1. Copy `Nexora-Stock-Check-Setup-<version>.exe` to the PC and run it
   (per-user install, no admin needed; pick the install folder if prompted).
2. Launch **Nexora Stock Check** from the Start Menu / desktop shortcut.
3. First run only — open **Settings** and set:
   - **API base URL** → the HO server, e.g. `http://<HO-SERVER-IP>:8000`
     (use the machine name or static IP HO is reachable at from the store LAN/VPN).
   - Click **Test connection** — expect "Connected successfully".
   - **Tenant ID / Store ID / Store Name** for this store (or use device
     activation → HO approves the device, which fills these in).
4. Sign in with the store's Nexora credentials. The app opens straight into
   Stock Availability.

Settings persist on that PC (localStorage in the app's userData), so steps 3–4
are one-time per machine.

## 3. Networking checklist (central HO model)

- HO backend must listen on `0.0.0.0:8000` (not just localhost) and its firewall
  must allow inbound 8000 from the store network.
- Store PCs must be able to reach the HO IP/host (same LAN, VPN, or a routed/static
  IP — see the HO multi-URL setup for failover routes).
- The app's CSP permits http/https/ws to any host, so any reachable HO URL works
  without a rebuild. Prefer HTTPS if HO is exposed beyond a trusted LAN.

## 4. Updating a deployed PC

Rebuild the installer with a bumped `version` in `package.json` and re-run it on the
PC (NSIS upgrades in place). No auto-update server is configured yet.
