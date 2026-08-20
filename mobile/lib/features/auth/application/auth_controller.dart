import 'package:flutter/foundation.dart' show defaultTargetPlatform;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/services/secure_storage_service.dart';
import 'package:nexora_mobile/features/auth/application/auth_state.dart';
import 'package:nexora_mobile/features/auth/data/auth_repository.dart';
import 'package:nexora_mobile/features/auth/data/models/app_user.dart';
import 'package:nexora_mobile/features/auth/data/models/user_role.dart';
import 'package:nexora_mobile/features/store_selection/data/store_repository.dart';

/// Owns the authentication session for the whole app: bootstrap on launch,
/// login, store selection, and logout. The router redirects off [AuthState].
final authControllerProvider =
    NotifierProvider<AuthController, AuthState>(AuthController.new);

class AuthController extends Notifier<AuthState> {
  final _log = AppLogger.of('AuthController');

  AuthRepository get _repo => ref.read(authRepositoryProvider);
  SecureStorageService get _storage => ref.read(secureStorageProvider);
  StoreRepository get _stores => ref.read(storeRepositoryProvider);

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
        device: DeviceDescriptor(
          deviceId: await _storage.ensureDeviceId(),
          platform: defaultTargetPlatform.name,
        ),
      );
      await _storage.writeToken(res.token);
      // Absent when talking to a server without the mobile BFF — the session
      // then simply cannot be refreshed (see AuthRepository.login).
      final refreshToken = res.refreshToken;
      if (refreshToken != null && refreshToken.isNotEmpty) {
        await _storage.writeRefreshToken(refreshToken);
      } else {
        _log.warning(
          'No refresh token issued — session will end at access-token expiry',
        );
      }
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

  /// Returns the active tenant, repairing incomplete selected-store data when
  /// necessary. Older cached sessions and slim store payloads may contain a
  /// store id without its tenant id; the full store endpoint is the canonical
  /// way to recover that association without making the user sign in again.
  Future<String?> resolveActiveTenantId() async {
    final current = state.activeTenantId;
    if (current != null) return current;

    final selected = state.selectedStore;
    if (selected == null || selected.storeId.trim().isEmpty) return null;

    try {
      final fullStore = await _stores.getById(selected.storeId);
      final tenantId = fullStore?.tenantId?.trim();
      if (tenantId == null || tenantId.isEmpty) return null;

      state = state.copyWith(
        selectedStore: selected.copyWith(tenantId: tenantId),
      );
      _log.info('Recovered tenant scope for store ${selected.storeId}');
      return tenantId;
    } on ApiException catch (e) {
      _log.warning(
        'Could not resolve tenant for store ${selected.storeId}: ${e.message}',
      );
      return null;
    }
  }

  /// Clear the store selection (return to the store picker) without logging out.
  Future<void> clearStore() async {
    await _storage.deleteSelectedStoreId();
    state = state.copyWith(selectedStore: null);
  }

  /// Full logout: revoke the refresh chain server-side, then wipe local state.
  ///
  /// The server call is best-effort — a user signing out on a train must still
  /// end up signed out locally. The access token stays valid until it expires
  /// either way; there is no denylist.
  Future<void> logout() async {
    final refreshToken = await _storage.readRefreshToken();
    final deviceId = await _storage.readDeviceId();
    if (refreshToken != null && refreshToken.isNotEmpty) {
      await _repo.logout(refreshToken: refreshToken, deviceId: deviceId);
    }
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
  /// still valid for this user (guards against stale selections).
  ///
  /// Store-scoped users are validated against their role entitlements (no
  /// extra request needed — same source `storeOptionsProvider` uses). A
  /// **platform user** has no store roles by definition (that's why they fell
  /// back to `/api/stores` to pick one in the first place), so a role-only
  /// check would always fail and silently drop their selection on every
  /// restart. For that case, validate directly against `GET /api/stores/{id}`
  /// instead — the same backend truth the picker itself relied on.
  Future<SelectedStore?> _restoreSelectedStore(AppUser user) async {
    final storedId = await _storage.readSelectedStoreId();
    if (storedId == null || storedId.isEmpty) return null;

    if (user.storeRoles.isNotEmpty) {
      final match = _findRoleStore(user, storedId);
      if (match == null) {
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

    try {
      final store = await _stores.getById(storedId);
      if (store == null || !store.isActive) {
        await _storage.deleteSelectedStoreId();
        return null;
      }
      return SelectedStore.fromStore(store);
    } on ApiException catch (e) {
      // Backend unreachable / transient error: keep the stored id rather than
      // wiping a possibly-still-valid selection, but don't block startup on
      // it — the store config sync will retry once the agent initializes.
      _log.warning('Could not verify stored store $storedId: ${e.message}');
      return null;
    }
  }

  UserRole? _findRoleStore(AppUser user, String storeId) {
    for (final r in user.storeRoles) {
      if (r.storeId == storeId) return r;
    }
    return null;
  }
}
