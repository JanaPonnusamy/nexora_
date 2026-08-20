# Privacy data inventory

This is an engineering inventory for Play Data safety and App Store Privacy.
The business/data owner must confirm collection, retention, legal basis,
sharing and deletion answers before submission.

| Data category | Purpose | Storage/transport | Notes to confirm |
|---|---|---|---|
| Account identifier and roles | Authentication and authorization | Secure OS keychain/keystore; HTTPS API | Retention and account-deletion process |
| Tenant and store assignment | Scope business data and sync | Local database; HTTPS API | Whether treated as user-linked data |
| Supplier invoices and photos | OCR extraction, review and export | Protected app storage; HTTPS upload | Server retention and deletion policy |
| Procurement quantities and supplier assignments | Purchase operations and audit | Offline outbox/local database; HTTPS API | Audit retention and role access |
| Device ID/model/app version | Device registration and support | Local secure storage/API | Exact identifier, retention and reset behavior |
| Diagnostics and crash details | Reliability and support | Local in-memory crash buffer | Buffer is cleared when the app process ends |
| Camera/photo-library access | Capture or select invoices | On-device until upload | Photos are user-initiated, not background collection |

Current safeguards:

- release networking rejects cleartext HTTP;
- authentication tokens use OS-backed secure storage;
- Android backup and device transfer are disabled for app data;
- iOS default data protection is explicitly enabled;
- supported offline mutations are visible and user-resolvable;
- release logs must never include tokens, passwords or invoice image content.

Open owner decisions:

- [ ] Public privacy-policy URL
- [ ] Support and privacy contact details
- [ ] Server-side retention/deletion periods per category
- [ ] Whether any processor receives data beyond the Axythic backend
