# 29 — Phase 7 Forgot Password SMTP sender
**NEXORA MEDIQ — transactional reset-code delivery**
Date: 2026-11-13

## 1. Scope

Phase 6 left `send_reset_email()` as an honest stub (doc 28 §9 and §14). This phase replaces that stub with stdlib SMTP + STARTTLS. No provider account was created, and no credential was written into the repo.

The desktop confirm step still asks the user to paste a code. The message body contains that code. It does not contain a clickable reset URL.

## 2. Configuration

These variables are independent of the store-to-HO file-transfer mailbox (`NEXORA_FILE_TRANSFER_SMTP_*`). Commented placeholders are in `backend/.env.example`.

| Variable | Role |
|---|---|
| `NEXORA_PASSWORD_RESET_SMTP_HOST` | SMTP host. Required. |
| `NEXORA_PASSWORD_RESET_SMTP_PORT` | Default `587`. |
| `NEXORA_PASSWORD_RESET_SMTP_USERNAME` | Login name. Required. |
| `NEXORA_PASSWORD_RESET_SMTP_FROM` | From header. Defaults to the username. |
| `NEXORA_PASSWORD_RESET_SMTP_PASSWORD` | Secret. Required unless the next variable names a different env var. |
| `NEXORA_PASSWORD_RESET_SMTP_PASSWORD_ENV` | Name of another environment variable that holds the secret. |
| `NEXORA_PASSWORD_RESET_SMTP_TIMEOUT` | Seconds. Default `20`. |

When host, username, or password is missing, or the port is not an integer in 1–65535, `send_reset_email()` returns `False` and does not open a socket. `request_reset()` still returns the generic message. The audit row's `email_delivered` flag stays `false`.

## 3. What the message contains

Subject: `NEXORA MEDIQ password reset code`.

Body: the account username, instructions that match the desktop path (Forgot password, then "I already have a reset code"), the raw token, and the 30-minute single-use expiry. The token and the SMTP password are not written to the log. Addresses containing CR or LF are refused before SMTP is contacted.

STARTTLS on the configured port is the only transport. Implicit SSL on port 465 is not implemented.

## 4. Security properties left unchanged

Token generation, SHA-256 storage, 30-minute expiry, single-use, the 3-per-hour rate limit, the generic HTTP response, password-strength checks, and session revocation are the Phase 6F behavior. The public request message now says "password reset code" so it matches the paste flow. A failed or unconfigured send does not change that public message.

## 5. Tests

| Suite | Command | Result |
|---|---|---|
| Password reset | `pytest tests/test_password_reset.py` | **25 passed** |
| Backend (full) | `pytest tests/` | **492 passed, 0 failed** (26 pre-existing warnings) |

New cases, all against a mocked `smtplib.SMTP`: unconfigured and partial config do not connect; a non-numeric port does not connect; a configured send calls `starttls`, `login`, and `send_message` and puts the code in the body; the password may be read from a named env var; an `SMTPAuthenticationError` returns `False`; a header-breaking address is refused. Log capture asserts the raw token and the password are absent.

No message was sent to a real mailbox. No SMTP host, username, or password was present for this work, so a live delivery was not observed.

## 6. Files changed

- `backend/modules/password_reset/service.py`
- `backend/tests/test_password_reset.py`
- `backend/.env.example`
- this report

## 7. Outstanding

- A real mailbox is not configured on this machine. Until `NEXORA_PASSWORD_RESET_SMTP_HOST`, `NEXORA_PASSWORD_RESET_SMTP_USERNAME`, and the password variable are set in the backend environment, reset requests still behave as "not delivered."
- The shared dev backend on `:8000` was not restarted, so it is still running the previous stub until that process reloads.
- The login button in `desktop/supplier-stock-client/src/App.jsx` still reads "Send reset link". The API message and the email body say "code". The button was left unchanged so this phase did not require an Electron click-through.
- Implicit TLS (port 465) is unsupported. Port 587 with STARTTLS is the supported mode.
- The confirm-failure text now says "reset code". That string is returned by the API; the desktop screen displays it as-is.

## FINAL VERDICT

**PARTIAL.** The sender is implemented and the mocked SMTP tests pass. A live send through a real provider was not run, because no provider or credential was supplied.
