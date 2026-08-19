import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:local_auth/local_auth.dart' show BiometricType;

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/security/app_lock_controller.dart';
import 'package:nexora_mobile/core/security/biometric_service.dart';
import 'package:nexora_mobile/core/security/presentation/app_lock_gate.dart';
import 'package:nexora_mobile/core/security/presentation/app_lock_screen.dart';
import 'package:nexora_mobile/core/services/secure_storage_service.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/auth/application/auth_state.dart';
import 'package:nexora_mobile/features/auth/data/models/app_user.dart';

class _FakeStorage extends SecureStorageService {
  _FakeStorage({bool enabled = false}) : _enabled = enabled;
  bool _enabled;

  @override
  Future<bool> readBiometricLockEnabled() async => _enabled;
  @override
  Future<void> writeBiometricLockEnabled(bool enabled) async =>
      _enabled = enabled;
}

class _FakeBiometrics extends BiometricService {
  _FakeBiometrics({this.outcome = UnlockOutcome.success});
  UnlockOutcome outcome;
  int prompts = 0;

  @override
  Future<BiometricCapability> capability() async => const BiometricCapability(
        hasBiometrics: true,
        hasDeviceCredential: true,
        types: [BiometricType.face],
      );

  @override
  Future<UnlockOutcome> authenticate({required String reason}) async {
    prompts++;
    return outcome;
  }
}

class _FakeAuthController extends AuthController {
  _FakeAuthController(this._state);
  final AuthState _state;

  @override
  AuthState build() => _state;
}

const _user = AppUser(userId: 'u1', username: 'clerk', roles: []);

void main() {
  testWidgets('the lock screen prompts on its own and offers a way out',
      (tester) async {
    final biometrics = _FakeBiometrics(outcome: UnlockOutcome.failed);
    final container = ProviderContainer(overrides: [
      secureStorageProvider.overrideWithValue(_FakeStorage(enabled: true)),
      biometricServiceProvider.overrideWithValue(biometrics),
    ]);
    addTearDown(container.dispose);
    await container.read(appLockControllerProvider.notifier).bootstrap();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AppLockScreen()),
      ),
    );
    await tester.pump();

    // Prompting without being asked is the point — an unlock screen whose first
    // step is "tap to be asked" is a step nobody wants.
    expect(biometrics.prompts, 1);

    await tester.pump();
    expect(find.text('Axythic is locked'), findsOneWidget);
    // Face unlock on this fake device, so the button must not say fingerprint.
    expect(find.text('Unlock with Face unlock'), findsOneWidget);
    // The escape hatch is what keeps a broken sensor from bricking the app.
    expect(find.text('Sign out instead'), findsOneWidget);
    expect(
      find.textContaining('not recognised'),
      findsOneWidget,
      reason: 'a failed attempt has to say so',
    );
  });

  testWidgets('the gate covers the app when locked and reveals it when not',
      (tester) async {
    final container = ProviderContainer(overrides: [
      secureStorageProvider.overrideWithValue(_FakeStorage(enabled: true)),
      biometricServiceProvider.overrideWithValue(
        _FakeBiometrics(outcome: UnlockOutcome.cancelled),
      ),
      authControllerProvider.overrideWith(
        () => _FakeAuthController(
          const AuthState(status: AuthStatus.authenticated, user: _user),
        ),
      ),
    ]);
    addTearDown(container.dispose);
    await container.read(appLockControllerProvider.notifier).bootstrap();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(
          home: AppLockGate(child: Text('sensitive invoice total')),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.text('Axythic is locked'), findsOneWidget);

    await container.read(appLockControllerProvider.notifier).setEnabled(false);
    await tester.pump();

    expect(find.text('Axythic is locked'), findsNothing);
    expect(find.text('sensitive invoice total'), findsOneWidget);
  });

  testWidgets(
      'the gate never covers a signed-out app — that would be a dead end for '
      'anyone who signed out with the lock on', (tester) async {
    final container = ProviderContainer(overrides: [
      secureStorageProvider.overrideWithValue(_FakeStorage(enabled: true)),
      biometricServiceProvider.overrideWithValue(_FakeBiometrics()),
      authControllerProvider.overrideWith(
        () => _FakeAuthController(
          const AuthState(status: AuthStatus.unauthenticated),
        ),
      ),
    ]);
    addTearDown(container.dispose);
    await container.read(appLockControllerProvider.notifier).bootstrap();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AppLockGate(child: Text('login form'))),
      ),
    );
    await tester.pump();

    expect(find.text('Axythic is locked'), findsNothing);
    expect(find.text('login form'), findsOneWidget);
  });

  testWidgets('the lock screen fits a 390x844 phone with nothing cut off',
      (tester) async {
    // The edit-sheet bug in §4 was exactly this: every assertion passed while
    // the primary action sat below the fold on a real display.
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final container = ProviderContainer(overrides: [
      secureStorageProvider.overrideWithValue(_FakeStorage(enabled: true)),
      biometricServiceProvider.overrideWithValue(
        _FakeBiometrics(outcome: UnlockOutcome.cancelled),
      ),
    ]);
    addTearDown(container.dispose);
    await container.read(appLockControllerProvider.notifier).bootstrap();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        // The real dark theme, because the sizing under test comes from it:
        // filled buttons carry minimumSize: Size.fromHeight(52).
        child: MaterialApp(theme: AppTheme.dark, home: const AppLockScreen()),
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(tester.takeException(), isNull);
    for (final label in ['Unlock with Face unlock', 'Sign out instead']) {
      final rect = tester.getRect(find.text(label));
      expect(rect.bottom, lessThanOrEqualTo(844),
          reason: '"$label" must be reachable on a 390x844 screen');
      expect(rect.top, greaterThanOrEqualTo(0));
    }
  });
}
