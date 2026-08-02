import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/services/secure_storage_service.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/auth/application/auth_state.dart';
import 'package:nexora_mobile/features/auth/data/auth_repository.dart';
import 'package:nexora_mobile/features/auth/data/models/app_user.dart';
import 'package:nexora_mobile/features/auth/data/models/user_role.dart';
import 'package:nexora_mobile/features/store_selection/data/models/store.dart';
import 'package:nexora_mobile/features/store_selection/data/store_repository.dart';

/// In-memory secure storage double. Every method is overridden below, so the
/// real `FlutterSecureStorage`/platform channel constructed by the superclass
/// is never actually touched.
class FakeSecureStorage extends SecureStorageService {
  final _store = <String, String>{};

  @override
  Future<String?> readToken() async => _store['token'];
  @override
  Future<void> writeToken(String token) async => _store['token'] = token;
  @override
  Future<void> deleteToken() async => _store.remove('token');

  @override
  Future<String?> readSelectedStoreId() async => _store['store'];
  @override
  Future<void> writeSelectedStoreId(String id) async => _store['store'] = id;
  @override
  Future<void> deleteSelectedStoreId() async => _store.remove('store');

  @override
  Future<void> clear() async {
    _store.remove('token');
    _store.remove('store');
  }
}

class FakeAuthRepository extends AuthRepository {
  FakeAuthRepository(this._user) : super(Dio());
  final AppUser _user;

  @override
  Future<AppUser> me() async => _user;
}

class FakeStoreRepository extends StoreRepository {
  FakeStoreRepository(this._store) : super(Dio());
  final Store? _store;

  @override
  Future<Store?> getById(String storeId) async =>
      _store?.storeId == storeId ? _store : null;
}

AppUser platformUser() => const AppUser(
      userId: 'u1',
      username: 'superadmin',
      isPlatformUser: true,
      roles: [], // platform users carry no store roles
    );

AppUser storeUser() => const AppUser(
      userId: 'u2',
      username: 'clerk',
      roles: [
        UserRole(
          roleId: 'r1',
          roleName: 'Clerk',
          storeId: 's1',
          storeCode: 'NMA',
          storeName: 'Nathan Medicals A',
        ),
      ],
    );

void main() {
  test(
    'a platform user (no store roles) keeps their selected store across a restart',
    () async {
      final storage = FakeSecureStorage();
      await storage.writeToken('tok');
      await storage.writeSelectedStoreId('s1');

      const store = Store(
        storeId: 's1',
        storeCode: 'NMA',
        storeName: 'Nathan Medicals A',
        isActive: true,
      );

      final container = ProviderContainer(overrides: [
        secureStorageProvider.overrideWithValue(storage),
        authRepositoryProvider
            .overrideWithValue(FakeAuthRepository(platformUser())),
        storeRepositoryProvider
            .overrideWithValue(FakeStoreRepository(store)),
      ],);
      addTearDown(container.dispose);

      await container.read(authControllerProvider.notifier).bootstrap();
      final state = container.read(authControllerProvider);

      expect(state.status, AuthStatus.authenticated);
      expect(state.selectedStore, isNotNull);
      expect(state.selectedStore!.storeId, 's1');
      expect(state.selectedStore!.storeName, 'Nathan Medicals A');
      // Regression guard: the old role-only check would have wiped this.
      expect(await storage.readSelectedStoreId(), 's1');
    },
  );

  test(
    'a platform user selection is dropped once the store no longer exists',
    () async {
      final storage = FakeSecureStorage();
      await storage.writeToken('tok');
      await storage.writeSelectedStoreId('gone');

      final container = ProviderContainer(overrides: [
        secureStorageProvider.overrideWithValue(storage),
        authRepositoryProvider
            .overrideWithValue(FakeAuthRepository(platformUser())),
        storeRepositoryProvider
            .overrideWithValue(FakeStoreRepository(null)),
      ],);
      addTearDown(container.dispose);

      await container.read(authControllerProvider.notifier).bootstrap();
      final state = container.read(authControllerProvider);

      expect(state.selectedStore, isNull);
      expect(await storage.readSelectedStoreId(), isNull);
    },
  );

  test('a store-scoped user is still validated against their roles', () async {
    final storage = FakeSecureStorage();
    await storage.writeToken('tok');
    await storage.writeSelectedStoreId('s1');

    final container = ProviderContainer(overrides: [
      secureStorageProvider.overrideWithValue(storage),
      authRepositoryProvider.overrideWithValue(FakeAuthRepository(storeUser())),
      // Should never be called for a role-matched store user.
      storeRepositoryProvider.overrideWithValue(FakeStoreRepository(null)),
    ],);
    addTearDown(container.dispose);

    await container.read(authControllerProvider.notifier).bootstrap();
    final state = container.read(authControllerProvider);

    expect(state.selectedStore?.storeId, 's1');
    expect(state.selectedStore?.storeName, 'Nathan Medicals A');
  });
}
