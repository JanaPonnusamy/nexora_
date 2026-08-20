import 'dart:io';

/// Fast, deterministic checks for release settings that are easy to regress
/// during a Flutter/Gradle/Xcode upgrade. Account-owned requirements (TLS,
/// signing keys, privacy-policy URL and store accounts) remain in store/README.
void main() {
  const checks = <_Check>[
    _Check(
      'android/app/build.gradle.kts',
      ['isMinifyEnabled = true', 'isShrinkResources = true'],
    ),
    _Check(
      'android/app/src/main/AndroidManifest.xml',
      [
        'android:allowBackup="false"',
        'android:usesCleartextTraffic="false"',
        'android:dataExtractionRules="@xml/data_extraction_rules"',
      ],
    ),
    _Check(
      'ios/Runner/Info.plist',
      [
        'ITSAppUsesNonExemptEncryption',
        'NSCameraUsageDescription',
        'NSPhotoLibraryUsageDescription',
        'NSFaceIDUsageDescription',
      ],
    ),
    _Check(
      'ios/Runner/Runner.entitlements',
      ['com.apple.developer.default-data-protection'],
    ),
    _Check(
      'ios/Runner.xcodeproj/project.pbxproj',
      ['CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements;'],
    ),
    _Check('store/listing_en-IN.md', ['# Axythic store listing']),
    _Check('store/privacy_data_inventory.md', ['# Privacy data inventory']),
    _Check(
      '../.github/workflows/mobile-ci.yml',
      [
        'flutter build appbundle --release',
        'secrets.AXYTHIC_API_BASE_URL',
        '--dart-define=NEXORA_ENV=prod',
      ],
    ),
  ];

  final failures = <String>[];
  for (final check in checks) {
    final file = File(check.path);
    if (!file.existsSync()) {
      failures.add('${check.path}: missing');
      continue;
    }
    final contents = file.readAsStringSync();
    for (final required in check.requiredText) {
      if (!contents.contains(required)) {
        failures.add('${check.path}: missing "$required"');
      }
    }
  }

  if (failures.isNotEmpty) {
    stderr.writeln('Release readiness checks failed:');
    for (final failure in failures) {
      stderr.writeln('  - $failure');
    }
    exitCode = 1;
    return;
  }
  stdout.writeln('Release readiness checks passed (${checks.length} files).');
}

class _Check {
  const _Check(this.path, this.requiredText);

  final String path;
  final List<String> requiredText;
}
