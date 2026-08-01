import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/services/secure_storage_service.dart';
import 'package:nexora_mobile/features/auth/application/auth_state.dart';
import 'package:nexora_mobile/features/auth/data/auth_repository.dart';
import 'package:nexora_mobile/features/auth/data/models/app_user.dart';
import 'package:nexora_mobile/features/auth/data/models/user_role.dart';

/// Owns the authentication session for the whole app: bootstrap on launch,
/// login, store selection, and logout. The router redirects off [AuthState].
final authControllerProvider =
    NotifierProvider<AuthController, AuthState>(AuthController.new);

class AuthController extends Notifier<AuthState> {
  final _log = AppLogger.of('AuthController');

  AuthRepository get _repo => ref.read(authRepositoryProvider);
  SecureStorageService get _storage => ref.read(secureStorageProvider);

  @override
  AuthState build() => const AuthState();

  /// Called once after the widget tree mounts. Restores a session from secure
  /// storage by validating the stored token against `/api/auth/me`.
  Future<void> bootstrap() async {
    final token = await _storage.readToken();
    if (token == null || token.isEmpty) {
      state = state.copyWith(status: AuthStatus.unauthenticated);
      return;
    }
    try {
      final user = await _repo.me();
      final selected = await _restoreSelectedStore(user);
      state = state.copyWith(
        status: AuthStatus.authenticated,
        user: user,
        selectedStore: selected,
      );
      _log.info('Session restored for ${user.username}');
    } on ApiException catch (e) {
      _log.info('Stored token rejected (${e.statusCode}); clearing session');
      await _storage.clear();
      state = const AuthState(status: AuthStatus.unauthenticated);
    }
  }

  /// Authenticate with the backend and persist the issued JWT.
  Future<bool> login({
    required String username,
    required String password,
  }) async {
    state = state.copyWith(busy: true, errorMessage: null);
    try {
      final res = await _repo.login(
        username: username.trim(),
        password: password,
      );
      await _storage.writeToken(res.token);
      final selected = await _restoreSelectedStore(res.user);
      state = state.copyWith(
        status: AuthStatus.authenticated,
        user: res.user,
        selectedStore: selected,
        busy: false,
      );
      return true;
    } on ApiException catch (e) {
      state = state.copyWith(busy: false, errorMessage: e.message);
      return false;
    }
  }

  /// Persist the user's chosen store and mark the session ready.
  Future<void> selectStore(SelectedStore store) async {
    await _storage.writeSelectedStoreId(store.storeId);
    state = state.copyWith(selectedStore: store);
    _log.info('Active store set to ${store.storeName} (${store.storeId})');
  }

  /// Clear the store selection (return to the store picker) without logging out.
  Future<void> clearStore() async {
    await _storage.deleteSelectedStoreId();
    state = state.copyWith(selectedStore: null);
  }

  /// Full logout: wipe token + selection and drop to the login screen.
  Future<void> logout() async {
    await _storage.clear();
    state = const AuthState(status: AuthStatus.unauthenticated);
  }

  /// Invoked by the Dio auth interceptor when the server returns 401 on an
  /// authenticated request (expired/invalid token).
  Future<void> onUnauthorized() async {
    if (state.status == AuthStatus.unauthenticated) return;
    _log.warning('401 from server — ending session');
    await logout();
  }

  void clearError() => state = state.copyWith(errorMessage: null);

  /// Re-hydrate the previously selected store from storage, but only if it is
  /// still a store the user is entitled to (guards against stale selections).
  Future<SelectedStore?> _restoreSelectedStore(AppUser user) async {
    final storedId = await _storage.readSelectedStoreId();
    if (storedId == null || storedId.isEmpty) return null;
    final match = _findRoleStore(user, storedId);
    if (match == null) {
      // Selection no longer valid for this user; drop it.
      await _storage.deleteSelectedStoreId();
      return null;
    }
    return SelectedStore(
      storeId: match.storeId!,
      storeName: match.storeName ?? match.storeCode ?? match.storeId!,
      storeCode: match.storeCode,
      tenantId: user.tenantId,
    );
  }

  UserRole? _findRoleStore(AppUser user, String storeId) {
    for (final r in user.storeRoles) {
      if (r.storeId == storeId) return r;
    }
    return null;
  }
}
