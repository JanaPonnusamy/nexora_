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
  static const _kStoreId = 'nexora.session.store_id';

  Future<String?> readToken() => _storage.read(key: _kToken);
  Future<void> writeToken(String token) =>
      _storage.write(key: _kToken, value: token);
  Future<void> deleteToken() => _storage.delete(key: _kToken);

  Future<String?> readSelectedStoreId() => _storage.read(key: _kStoreId);
  Future<void> writeSelectedStoreId(String storeId) =>
      _storage.write(key: _kStoreId, value: storeId);
  Future<void> deleteSelectedStoreId() => _storage.delete(key: _kStoreId);

  /// Full wipe on logout.
  Future<void> clear() async {
    await deleteToken();
    await deleteSelectedStoreId();
  }
}
