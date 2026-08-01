import 'package:freezed_annotation/freezed_annotation.dart';

import 'package:nexora_mobile/features/auth/data/models/app_user.dart';
import 'package:nexora_mobile/features/store_selection/data/models/store.dart';

part 'auth_state.freezed.dart';

/// Lifecycle of the auth session.
enum AuthStatus {
  /// Startup: still resolving whether a stored token is valid.
  unknown,

  /// No valid session — show login.
  unauthenticated,

  /// Token valid, user loaded. A store may or may not be selected yet.
  authenticated,
}

@freezed
class AuthState with _$AuthState {
  const AuthState._();

  const factory AuthState({
    @Default(AuthStatus.unknown) AuthStatus status,
    AppUser? user,

    /// The store the user is currently operating within. Null until chosen on
    /// the store-selection screen.
    SelectedStore? selectedStore,

    /// True while a login / validation request is in flight.
    @Default(false) bool busy,

    /// Last user-facing error (e.g. bad credentials), cleared on retry.
    String? errorMessage,
  }) = _AuthState;

  bool get isAuthenticated => status == AuthStatus.authenticated;
  bool get hasStore => selectedStore != null;

  /// True once the user is authenticated AND has picked a store — the point at
  /// which the app shell (dashboard) becomes reachable.
  bool get isReady => isAuthenticated && hasStore;
}

/// Minimal, serialisable description of the active store. Sourced either from a
/// user role or from `/api/stores`.
@freezed
class SelectedStore with _$SelectedStore {
  const SelectedStore._();

  const factory SelectedStore({
    required String storeId,
    required String storeName,
    String? storeCode,
    String? tenantId,
  }) = _SelectedStore;

  factory SelectedStore.fromStore(Store store) => SelectedStore(
        storeId: store.storeId,
        storeName: store.storeName,
        storeCode: store.storeCode,
        tenantId: store.tenantId,
      );
}
