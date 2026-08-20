import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/auth/application/auth_state.dart';
import 'package:nexora_mobile/features/auth/data/models/app_user.dart';
import 'package:nexora_mobile/features/auth/data/models/user_role.dart';
import 'package:nexora_mobile/features/store_selection/application/store_options_provider.dart';
import 'package:nexora_mobile/features/store_selection/data/models/store.dart';
import 'package:nexora_mobile/features/store_selection/data/store_repository.dart';
import 'package:nexora_mobile/features/store_selection/presentation/store_selection_screen.dart';

const _stores = [
  Store(
    storeId: 's-c',
    storeCode: 'NMC',
    storeName: 'Nathan Medicals C',
  ),
  Store(
    storeId: 's-a',
    storeCode: 'NMA',
    storeName: 'Nathan Medicals A',
  ),
  Store(
    storeId: 's-disabled',
    storeCode: 'NMX',
    storeName: 'Nathan Medicals Disabled',
    isActive: false,
  ),
];

class _StoreRepository extends StoreRepository {
  _StoreRepository() : super(Dio());

  var getAllCalls = 0;

  @override
  Future<List<Store>> getAll() async {
    getAllCalls++;
    return _stores;
  }
}

class _SeededAuthController extends AuthController {
  @override
  AuthState build() => const AuthState(
        status: AuthStatus.authenticated,
        user: AppUser(
          userId: 'super-1',
          username: 'Super',
          isPlatformUser: true,
          roles: [
            UserRole(
              roleId: 'role-a',
              roleName: 'Manager',
              storeId: 's-a',
              storeCode: 'NMA',
              storeName: 'Nathan Medicals A',
            ),
          ],
        ),
      );

  @override
  Future<void> selectStore(SelectedStore store) async {
    state = state.copyWith(selectedStore: store);
  }
}

void main() {
  test(
    'platform user sees every active store even when they also have a store role',
    () async {
      final repository = _StoreRepository();
      final container = ProviderContainer(
        overrides: [
          authControllerProvider.overrideWith(_SeededAuthController.new),
          storeRepositoryProvider.overrideWithValue(repository),
        ],
      );
      addTearDown(container.dispose);

      final options = await container.read(storeOptionsProvider.future);

      expect(options.map((store) => store.storeCode), ['NMA', 'NMC']);
      expect(repository.getAllCalls, 1);
    },
  );

  testWidgets('each store card selects its own store', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith(_SeededAuthController.new),
        storeOptionsProvider.overrideWith(
          (_) async => const [
            SelectedStore(
              storeId: 's-a',
              storeCode: 'NMA',
              storeName: 'Nathan Medicals A',
            ),
            SelectedStore(
              storeId: 's-c',
              storeCode: 'NMC',
              storeName: 'Nathan Medicals C',
            ),
          ],
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          theme: AppTheme.dark,
          home: const StoreSelectionScreen(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Nathan Medicals A'), findsOneWidget);
    expect(find.text('Nathan Medicals C'), findsOneWidget);

    await tester.tap(find.text('Nathan Medicals C'));
    await tester.pump();

    expect(
      container.read(authControllerProvider).selectedStore?.storeId,
      's-c',
    );
  });
}
