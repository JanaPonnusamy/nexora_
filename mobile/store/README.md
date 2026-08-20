# Axythic mobile release checklist

Phase 6 code hardening is automated by `dart run tool/verify_release_readiness.dart`.
Publishing still requires account owners and production infrastructure; do not
replace these with dummy values merely to make a checklist green.

## Required before either store submission

- [ ] Production API is available over HTTPS and the production build uses its
      HTTPS URL. Cleartext is intentionally blocked in release builds. Add the
      URL as the `AXYTHIC_API_BASE_URL` repository secret; signed CI builds fail
      when it is absent or is not HTTPS.
- [ ] Rotate the exposed production JWT/setup/SQL credentials described in
      `docs/AXYTHIC_MOBILE_HANDOFF.md`.
- [ ] Approve and publish a public privacy-policy URL.
- [ ] Complete the data-safety/privacy answers using
      `privacy_data_inventory.md`, validated by the business/data owner.
- [ ] Capture final phone screenshots from production-like data with all
      patient, supplier and credential information anonymised.
- [ ] Validate camera orientation, invoice quality thresholds and offline
      recovery on at least one physical Android and one physical iPhone.
- [ ] Run a deliberate Stock Distribution acceptance test in a non-production
      tenant before enabling it for production roles.

## Google Play

- [ ] Create the Play Console app for `com.axythic.mobile`.
- [ ] Generate and securely back up the upload keystore; populate the
      `AXYTHIC_KEYSTORE_*` repository secrets.
- [ ] Enrol in Play App Signing and upload an AAB built with
      `AXYTHIC_REQUIRE_RELEASE_SIGNING=true`.
- [ ] Complete Data safety, App access (test credentials), content rating and
      target-audience declarations.
- [ ] Start with Internal testing, then Closed testing, then a staged production
      rollout with crash/login/sync/OCR/distribution monitoring at every gate.

## App Store Connect

- [ ] Create the app for bundle ID `com.axythic.mobile` and configure the Apple
      team, distribution certificate and App Store provisioning profile.
- [ ] Complete App Privacy, age rating, review notes and test credentials.
- [ ] Upload through TestFlight first; verify camera/photo picker, Face ID,
      workbook sharing and background/foreground lock behavior on hardware.
- [ ] Release manually or as a phased release only after TestFlight acceptance.

Primary platform references:

- [Android shrink/optimize](https://developer.android.com/build/shrink-code)
- [Android backup controls](https://developer.android.com/guide/topics/data/autobackup)
- [Apple App Privacy](https://developer.apple.com/app-store/app-privacy-details/)
- [Flutter accessibility](https://docs.flutter.dev/ui/accessibility-and-internationalization/accessibility)
