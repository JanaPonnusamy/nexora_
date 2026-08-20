import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:local_auth/local_auth.dart' show BiometricType;

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/security/app_lock_controller.dart';
import 'package:nexora_mobile/core/security/biometric_service.dart';
import 'package:nexora_mobile/core/services/secure_storage_service.dart';

/// In-memory double. Every method used by the controller is overridden, so the
/// real platform channel the superclass builds is never touched.
class _FakeStorage extends SecureStorageService {
  _FakeStorage({bool enabled = false}) : _enabled = enabled;

  bool _enabled;
  int writes = 0;

  @override
  Future<bool> readBiometricLockEnabled() async => _enabled;

  @override
  Future<void> writeBiometricLockEnabled(bool enabled) async {
    writes++;
    _enabled = enabled;
  }
}

class _FakeBiometrics extends BiometricService {
  _FakeBiometrics({
    this.capabilityResult = const BiometricCapability(
      hasBiometrics: true,
      hasDeviceCredential: true,
      types: [BiometricType.fingerprint],
    ),
    this.outcome = UnlockOutcome.success,
  });

  BiometricCapability capabilityResult;
  UnlockOutcome outcome;
  int prompts = 0;

  @override
  Future<BiometricCapability> capability() async => capabilityResult;

  @override
  Future<UnlockOutcome> authenticate({required String reason}) async {
    prompts++;
    return outcome;
  }
}

ProviderContainer _container({
  required _FakeStorage storage,
  required _FakeBiometrics biometrics,
}) {
  final container = ProviderContainer(
    overrides: [
      secureStorageProvider.overrideWithValue(storage),
      biometricServiceProvider.overrideWithValue(biometrics),
    ],
  );
  addTearDown(container.dispose);
  return container;
}

void main() {
  group('bootstrap', () {
    test('a disabled preference leaves the app unlocked', () async {
      final container = _container(
        storage: _FakeStorage(),
        biometrics: _FakeBiometrics(),
      );
      await container.read(appLockControllerProvider.notifier).bootstrap();

      final state = container.read(appLockControllerProvider);
      expect(state.enabled, isFalse);
      expect(state.locked, isFalse);
      expect(state.initialised, isTrue);
    });

    test('an enabled preference locks before any content is shown', () async {
      final container = _container(
        storage: _FakeStorage(enabled: true),
        biometrics: _FakeBiometrics(),
      );
      await container.read(appLockControllerProvider.notifier).bootstrap();

      final state = container.read(appLockControllerProvider);
      expect(state.enabled, isTrue);
      expect(state.locked, isTrue);
    });

    test(
      'the preference stands down when the device credential is gone — '
      'a lock screen nothing can satisfy is a bricked app',
      () async {
        final storage = _FakeStorage(enabled: true);
        final container = _container(
          storage: storage,
          biometrics: _FakeBiometrics(
            capabilityResult: const BiometricCapability.none(),
          ),
        );
        await container.read(appLockControllerProvider.notifier).bootstrap();

        final state = container.read(appLockControllerProvider);
        expect(state.enabled, isFalse);
        expect(state.locked, isFalse);
        expect(await storage.readBiometricLockEnabled(), isFalse,
            reason: 'the stale preference must be cleared, not just ignored');
      },
    );
  });

  group('setEnabled', () {
    test('enabling proves the prompt works before persisting', () async {
      final storage = _FakeStorage();
      final biometrics = _FakeBiometrics();
      final container = _container(storage: storage, biometrics: biometrics);

      final outcome = await container
          .read(appLockControllerProvider.notifier)
          .setEnabled(true);

      expect(outcome, UnlockOutcome.success);
      expect(biometrics.prompts, 1);
      expect(await storage.readBiometricLockEnabled(), isTrue);
      expect(container.read(appLockControllerProvider).enabled, isTrue);
    });

    test('a cancelled prompt does not turn the lock on', () async {
      final storage = _FakeStorage();
      final container = _container(
        storage: storage,
        biometrics: _FakeBiometrics(outcome: UnlockOutcome.cancelled),
      );

      final outcome = await container
          .read(appLockControllerProvider.notifier)
          .setEnabled(true);

      expect(outcome, UnlockOutcome.cancelled);
      expect(await storage.readBiometricLockEnabled(), isFalse);
      expect(container.read(appLockControllerProvider).enabled, isFalse);
    });

    test('an unsupported device is refused without prompting', () async {
      final biometrics = _FakeBiometrics(
        capabilityResult: const BiometricCapability.none(),
      );
      final container = _container(
        storage: _FakeStorage(),
        biometrics: biometrics,
      );

      final outcome = await container
          .read(appLockControllerProvider.notifier)
          .setEnabled(true);

      expect(outcome, UnlockOutcome.unavailable);
      expect(biometrics.prompts, 0);
    });

    test('disabling unlocks immediately', () async {
      final container = _container(
        storage: _FakeStorage(enabled: true),
        biometrics: _FakeBiometrics(),
      );
      final notifier = container.read(appLockControllerProvider.notifier);
      await notifier.bootstrap();
      expect(container.read(appLockControllerProvider).locked, isTrue);

      await notifier.setEnabled(false);

      expect(container.read(appLockControllerProvider).locked, isFalse);
      expect(container.read(appLockControllerProvider).enabled, isFalse);
    });
  });

  group('unlock', () {
    test('success clears the lock', () async {
      final container = _container(
        storage: _FakeStorage(enabled: true),
        biometrics: _FakeBiometrics(),
      );
      final notifier = container.read(appLockControllerProvider.notifier);
      await notifier.bootstrap();

      await notifier.unlock();

      expect(container.read(appLockControllerProvider).locked, isFalse);
    });

    test('a failed attempt keeps the lock and records why', () async {
      final container = _container(
        storage: _FakeStorage(enabled: true),
        biometrics: _FakeBiometrics(outcome: UnlockOutcome.failed),
      );
      final notifier = container.read(appLockControllerProvider.notifier);
      await notifier.bootstrap();

      await notifier.unlock();

      final state = container.read(appLockControllerProvider);
      expect(state.locked, isTrue);
      expect(state.lastOutcome, UnlockOutcome.failed);
      expect(state.authenticating, isFalse);
    });

    test(
      'losing the credential while locked releases the app rather than '
      'stranding a valid session behind a prompt that cannot succeed',
      () async {
        final storage = _FakeStorage(enabled: true);
        final biometrics = _FakeBiometrics();
        final container = _container(storage: storage, biometrics: biometrics);
        final notifier = container.read(appLockControllerProvider.notifier);
        await notifier.bootstrap();

        biometrics.outcome = UnlockOutcome.unavailable;
        await notifier.unlock();

        final state = container.read(appLockControllerProvider);
        expect(state.locked, isFalse);
        expect(state.enabled, isFalse);
        expect(await storage.readBiometricLockEnabled(), isFalse);
      },
    );

    test('unlock is a no-op when not locked', () async {
      final biometrics = _FakeBiometrics();
      final container = _container(
        storage: _FakeStorage(),
        biometrics: biometrics,
      );
      final notifier = container.read(appLockControllerProvider.notifier);
      await notifier.bootstrap();

      await notifier.unlock();

      expect(biometrics.prompts, 0);
    });
  });

  group('lifecycle', () {
    late ProviderContainer container;
    late AppLockController notifier;
    final t0 = DateTime(2026, 8, 17, 9);

    Future<void> setUpLocked() async {
      container = _container(
        storage: _FakeStorage(enabled: true),
        biometrics: _FakeBiometrics(),
      );
      notifier = container.read(appLockControllerProvider.notifier);
      await notifier.bootstrap();
      await notifier.unlock(); // start from unlocked, as after a real unlock
    }

    test('a short trip away does not re-lock', () async {
      await setUpLocked();

      notifier.onLifecycleChange(AppLifecycleState.paused, now: t0);
      notifier.onLifecycleChange(
        AppLifecycleState.resumed,
        now: t0.add(const Duration(seconds: 5)),
      );

      expect(container.read(appLockControllerProvider).locked, isFalse,
          reason: 'a share sheet must not cost the user a re-auth');
    });

    test('past the grace period it re-locks', () async {
      await setUpLocked();

      notifier.onLifecycleChange(AppLifecycleState.paused, now: t0);
      notifier.onLifecycleChange(
        AppLifecycleState.resumed,
        now: t0.add(kAppLockGracePeriod + const Duration(seconds: 1)),
      );

      expect(container.read(appLockControllerProvider).locked, isTrue);
    });

    test(
      'the first background stamp wins — iOS emits hidden then paused, and '
      'restamping would push the deadline forward forever',
      () async {
        await setUpLocked();

        notifier.onLifecycleChange(AppLifecycleState.hidden, now: t0);
        notifier.onLifecycleChange(
          AppLifecycleState.paused,
          now: t0.add(const Duration(seconds: 25)),
        );
        notifier.onLifecycleChange(
          AppLifecycleState.resumed,
          now: t0.add(const Duration(seconds: 31)),
        );

        expect(container.read(appLockControllerProvider).locked, isTrue);
      },
    );

    test('inactive alone never locks — it is a notification shade, not an exit',
        () async {
      await setUpLocked();

      notifier.onLifecycleChange(AppLifecycleState.inactive, now: t0);
      notifier.onLifecycleChange(
        AppLifecycleState.resumed,
        now: t0.add(const Duration(minutes: 10)),
      );

      expect(container.read(appLockControllerProvider).locked, isFalse);
    });

    test('lifecycle is ignored entirely when the feature is off', () async {
      container = _container(
        storage: _FakeStorage(),
        biometrics: _FakeBiometrics(),
      );
      notifier = container.read(appLockControllerProvider.notifier);
      await notifier.bootstrap();

      notifier.onLifecycleChange(AppLifecycleState.paused, now: t0);
      notifier.onLifecycleChange(
        AppLifecycleState.resumed,
        now: t0.add(const Duration(hours: 1)),
      );

      expect(container.read(appLockControllerProvider).locked, isFalse);
    });
  });
}
