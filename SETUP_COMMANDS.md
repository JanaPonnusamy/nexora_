# Nexora — Setup & Run Commands

> Backend URL: `http://122.252.246.181:8443`

---

## 1. Backend (Python / FastAPI)

```bash
# Prerequisites for macOS:
# Install unixodbc (required by pyodbc for SQL Server DB connections)
brew install unixodbc

# Navigate to backend
cd nexora_/backend

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# macOS / Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies (use pip3 or pip inside activated venv)
pip3 install -r requirements.txt

# Install Playwright browser (one-time, needed by some modules)
python3 -m playwright install firefox

# Run the backend server (dev)
python3 -m uvicorn api.app:app --host 0.0.0.0 --port 8443 --reload
```

---

## 2. Frontend (Vite + React + TypeScript)

```bash
# Navigate to frontend
cd nexora_/frontend

# Install dependencies
npm install

# Run dev server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

---

## 3. Desktop — Supplier Stock Client (Vite + React + Electron)

```bash
# Navigate to desktop client
cd nexora_/desktop/supplier-stock-client

# Install dependencies
npm install

# Run in dev mode (Vite + Electron concurrently)
npm run dev

# Build for production
npm run build

# Launch Electron app directly
npm start
```

---

## 4. Mobile (Flutter / Dart)

```bash
# Navigate to mobile
cd nexora_/mobile

# Get Flutter dependencies
flutter pub get

# Run code generation (freezed, json_serializable, riverpod, drift)
dart run build_runner build --delete-conflicting-outputs

# Run on connected device / emulator
flutter run

# Run with custom backend URL override (if not using the default)
flutter run --dart-define=NEXORA_API_BASE_URL=http://122.252.246.181:8443

# Build APK (Android)
flutter build apk

# Build iOS
flutter build ios
```

---

## Environment Files

| File | Purpose |
|------|---------|
| `backend/.env` | Backend config (DB, JWT, CORS, API URL) |
| `backend/.env.example` | Template with all available env variables |
| `backend/config/ho.env` | HO deployment-specific overrides |

### Key Environment Variables

```env
# Database
DB_SERVER=192.168.10.73
DB_DATABASE=NEXORA_PLATFORM
DB_USERNAME=sa
DB_PASSWORD=Admin123

# API URL (baked into frontend via /config.js)
UNINEX_API_URL=http://122.252.246.181:8443

# CORS (allowed origins)
UNINEX_CORS_ORIGINS=http://192.168.10.80:8443,http://122.252.246.181:8443,null

# JWT
UNINEX_JWT_SECRET=<your-secret>
UNINEX_JWT_EXPIRE_MINUTES=720
```

---

## Quick Start (All Services)

```bash
# Terminal 1 — Backend
cd nexora_/backend
source .venv/bin/activate
uvicorn api.app:app --host 0.0.0.0 --port 8443 --reload

# Terminal 2 — Frontend
cd nexora_/frontend
npm install
npm run dev

# Terminal 3 — Mobile
cd nexora_/mobile
flutter pub get
flutter run
```
