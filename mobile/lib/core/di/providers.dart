import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/config/app_config.dart';
import 'package:nexora_mobile/core/network/dio_client.dart';
import 'package:nexora_mobile/core/services/secure_storage_service.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/auth/data/auth_repository.dart';
import 'package:nexora_mobile/features/store_selection/data/store_repository.dart';

/// Root dependency-injection graph for the app. Everything is wired through
/// Riverpod providers so construction stays lazy, single-instance and testable
/// (override any provider in tests).

/// Resolved, environment-specific configuration. Overridden in `bootstrap`.
final appConfigProvider = Provider<AppConfig>(
  (ref) => throw UnimplementedError('appConfigProvider must be overridden'),
);

/// Secure storage (Keychain / Keystore) for the JWT and selected store.
final secureStorageProvider = Provider<SecureStorageService>(
  (ref) => SecureStorageService(),
);

/// The single shared Dio instance. Its auth interceptor calls back into the
/// [authControllerProvider] to tear the session down on a 401.
final dioProvider = Provider<Dio>((ref) {
  final config = ref.watch(appConfigProvider);
  final storage = ref.watch(secureStorageProvider);
  return DioClient.create(
    config: config,
    storage: storage,
    onUnauthorized: () async {
      await ref.read(authControllerProvider.notifier).onUnauthorized();
    },
  );
});

/// Repositories.
final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(ref.watch(dioProvider)),
);

final storeRepositoryProvider = Provider<StoreRepository>(
  (ref) => StoreRepository(ref.watch(dioProvider)),
);
