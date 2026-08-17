import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Wraps `flutter_secure_storage` behind a small, testable surface.
///
/// Backed by the Android Keystore / iOS Keychain. Holds the JWT and the
/// user's last selected store id so the session survives app restarts within
/// the token's lifetime.
class SecureStorageService {
  SecureStorageService([FlutterSecureStorage? storage])
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
              iOptions: IOSOptions(
                accessibility: KeychainAccessibility.first_unlock,
              ),
            );

  final FlutterSecureStorage _storage;

  static const _kToken = 'nexora.auth.token';
  static const _kRefreshToken = 'nexora.auth.refresh_token';
  static const _kStoreId = 'nexora.session.store_id';
  static const _kDeviceId = 'nexora.device.id';

  Future<String?> readToken() => _storage.read(key: _kToken);
  Future<void> writeToken(String token) =>
      _storage.write(key: _kToken, value: token);
  Future<void> deleteToken() => _storage.delete(key: _kToken);

  /// Long-lived credential used to mint a new access token once the 12-hour
  /// one expires. Rotated on every use by the server, so the stored value must
  /// be replaced — never appended to — after each refresh.
  Future<String?> readRefreshToken() => _storage.read(key: _kRefreshToken);
  Future<void> writeRefreshToken(String token) =>
      _storage.write(key: _kRefreshToken, value: token);
  Future<void> deleteRefreshToken() => _storage.delete(key: _kRefreshToken);

  Future<String?> readSelectedStoreId() => _storage.read(key: _kStoreId);
  Future<void> writeSelectedStoreId(String storeId) =>
      _storage.write(key: _kStoreId, value: storeId);
  Future<void> deleteSelectedStoreId() => _storage.delete(key: _kStoreId);

  /// Stable per-installation device identity. Survives logout (only cleared on
  /// uninstall) so the agent keeps the same device id across sessions.
  Future<String?> readDeviceId() => _storage.read(key: _kDeviceId);
  Future<void> writeDeviceId(String id) =>
      _storage.write(key: _kDeviceId, value: id);

  /// Returns the device id, minting one on first call.
  ///
  /// Login needs this before the agent has booted (the agent only starts once
  /// a session is ready), and a refresh-token chain is bound to it — so both
  /// paths must agree on the same value.
  Future<String> ensureDeviceId() async {
    final existing = await readDeviceId();
    if (existing != null && existing.isNotEmpty) return existing;
    final generated = generateUuidV4();
    await writeDeviceId(generated);
    return generated;
  }

  /// RFC-4122 v4 UUID from a cryptographically-secure RNG (no extra deps).
  static String generateUuidV4() {
    final rng = Random.secure();
    final bytes = List<int>.generate(16, (_) => rng.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
    bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10xx
    String hex(int start, int end) => bytes
        .sublist(start, end)
        .map((b) => b.toRadixString(16).padLeft(2, '0'))
        .join();
    return '${hex(0, 4)}-${hex(4, 6)}-${hex(6, 8)}-${hex(8, 10)}-${hex(10, 16)}';
  }

  /// Wipe on logout. The device id is intentionally preserved.
  Future<void> clear() async {
    await deleteToken();
    await deleteRefreshToken();
    await deleteSelectedStoreId();
  }
}
