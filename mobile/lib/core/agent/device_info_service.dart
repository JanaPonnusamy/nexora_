import 'package:device_info_plus/device_info_plus.dart';
import 'package:drift/drift.dart' show Value;
import 'package:flutter/foundation.dart';
import 'package:package_info_plus/package_info_plus.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/services/secure_storage_service.dart';
import 'package:nexora_mobile/core/sync/sync_repository.dart';

/// Resolved identity of this installation.
class DeviceIdentity {
  const DeviceIdentity({
    required this.deviceId,
    required this.platform,
    required this.model,
    required this.osVersion,
    required this.appVersion,
    required this.buildNumber,
    required this.registeredAt,
    required this.lastSeenAt,
  });

  final String deviceId;
  final String platform;
  final String model;
  final String osVersion;
  final String appVersion;
  final String buildNumber;
  final DateTime registeredAt;
  final DateTime lastSeenAt;

  String get versionLabel =>
      buildNumber.isEmpty ? appVersion : '$appVersion ($buildNumber)';
}

/// Establishes and persists the device identity used by the Legacy Store Agent.
///
/// Registration is a LOCAL concern: we mint a stable device id (kept in secure
/// storage), enrich it with real platform/app metadata, and cache it in the
/// `device_information` table so the Device Status screen works fully offline
/// and the identity survives restarts. (There is no mobile-device registry
/// endpoint on the backend — see docs/API_CONTRACT.md.)
class DeviceInfoService {
  DeviceInfoService(
    this._repo,
    this._storage, {
    DeviceInfoPlugin? deviceInfoPlugin,
  }) : _deviceInfo = deviceInfoPlugin ?? DeviceInfoPlugin();

  final SyncRepository _repo;
  final SecureStorageService _storage;
  final DeviceInfoPlugin _deviceInfo;
  final _log = AppLogger.of('DeviceInfo');

  /// Loads the cached identity without touching platform channels.
  Future<DeviceIdentity?> cached() async {
    final row = await _repo.readDevice();
    if (row == null) return null;
    return _fromRow(row);
  }

  /// Ensures a device identity exists, refreshing volatile fields (app version,
  /// last-seen) and persisting it. Idempotent and safe to call every launch.
  Future<DeviceIdentity> registerOrRefresh() async {
    final now = DateTime.now();
    final existing = await _repo.readDevice();

    final deviceId = await _resolveDeviceId();
    final meta = await _collectPlatformMeta();
    final appInfo = await _collectAppInfo();

    final identity = DeviceIdentity(
      deviceId: deviceId,
      platform: meta.$1,
      model: meta.$2,
      osVersion: meta.$3,
      appVersion: appInfo.$1,
      buildNumber: appInfo.$2,
      registeredAt: existing?.registeredAt ?? now,
      lastSeenAt: now,
    );

    await _repo.upsertDevice(
      DeviceInformationCompanion(
        deviceId: Value(identity.deviceId),
        platform: Value(identity.platform),
        model: Value(identity.model),
        osVersion: Value(identity.osVersion),
        appVersion: Value(identity.appVersion),
        buildNumber: Value(identity.buildNumber),
        registeredAt: Value(identity.registeredAt),
        lastSeenAt: Value(identity.lastSeenAt),
      ),
    );

    _log.info('Device ${identity.deviceId} (${identity.platform}) refreshed');
    return identity;
  }

  Future<void> touch() => _repo.touchDeviceSeen(DateTime.now());

  // Delegates so the agent and the login flow cannot mint different ids for
  // the same install — a refresh-token chain is bound to this value.
  Future<String> _resolveDeviceId() => _storage.ensureDeviceId();

  /// Returns (platform, model, osVersion).
  Future<(String, String, String)> _collectPlatformMeta() async {
    try {
      if (kIsWeb) {
        final info = await _deviceInfo.webBrowserInfo;
        return (
          'web',
          info.browserName.name,
          info.appVersion ?? info.userAgent ?? '',
        );
      }
      switch (defaultTargetPlatform) {
        case TargetPlatform.android:
          final a = await _deviceInfo.androidInfo;
          return (
            'android',
            '${a.manufacturer} ${a.model}',
            'Android ${a.version.release} (API ${a.version.sdkInt})'
          );
        case TargetPlatform.iOS:
          final i = await _deviceInfo.iosInfo;
          return (
            'ios',
            i.utsname.machine,
            '${i.systemName} ${i.systemVersion}'
          );
        case TargetPlatform.windows:
          final w = await _deviceInfo.windowsInfo;
          return ('windows', w.computerName, 'Windows ${w.displayVersion}');
        case TargetPlatform.macOS:
          final m = await _deviceInfo.macOsInfo;
          return ('macos', m.model, 'macOS ${m.osRelease}');
        case TargetPlatform.linux:
          final l = await _deviceInfo.linuxInfo;
          return ('linux', l.prettyName, l.version ?? '');
        default:
          return (defaultTargetPlatform.name, '', '');
      }
    } catch (e) {
      _log.warning('Platform metadata unavailable: $e');
      return (kIsWeb ? 'web' : defaultTargetPlatform.name, '', '');
    }
  }

  /// Returns (appVersion, buildNumber).
  Future<(String, String)> _collectAppInfo() async {
    try {
      final info = await PackageInfo.fromPlatform();
      return (info.version, info.buildNumber);
    } catch (e) {
      _log.warning('Package info unavailable: $e');
      return ('', '');
    }
  }

  DeviceIdentity _fromRow(DeviceInformationData row) => DeviceIdentity(
        deviceId: row.deviceId,
        platform: row.platform,
        model: row.model,
        osVersion: row.osVersion,
        appVersion: row.appVersion,
        buildNumber: row.buildNumber,
        registeredAt: row.registeredAt,
        lastSeenAt: row.lastSeenAt,
      );
}
