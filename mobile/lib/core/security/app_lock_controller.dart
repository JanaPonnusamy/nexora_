import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/security/biometric_service.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/services/secure_storage_service.dart';

/// How long the app may sit in the background before it re-locks.
///
/// Not zero. Exporting a workbook, picking a photo, and answering a permission
/// dialog all background the app for a second or two, and re-prompting on the
/// way back trains people to turn the feature off — which is a worse security
/// outcome than the gap. Long enough to cover a share sheet, short enough that a
/// phone left on a counter is not open to whoever picks it up.
const kAppLockGracePeriod = Duration(seconds: 30);

class AppLockState {
  const AppLockState({
    this.enabled = false,
    this.locked = false,
    this.authenticating = false,
    this.capability = const BiometricCapability.none(),
    this.lastOutcome,
    this.initialised = false,
  });

  /// The user's preference, restored from secure storage.
  final bool enabled;

  /// The lock screen is covering the app right now.
  final bool locked;

  /// A prompt is on screen. Guards against firing two at once, which on Android
  /// cancels the first and looks like a spontaneous failure.
  final bool authenticating;

  final BiometricCapability capability;

  /// Result of the most recent attempt, so the lock screen can explain itself.
  final UnlockOutcome? lastOutcome;

  /// False until the stored preference has been read. The gate must not render
  /// an unlocked app in the meantime, or a locked app flashes its contents on
  /// every cold start.
  final bool initialised;

  AppLockState copyWith({
    bool? enabled,
    bool? locked,
    bool? authenticating,
    BiometricCapability? capability,
    UnlockOutcome? lastOutcome,
    bool clearOutcome = false,
    bool? initialised,
  }) =>
      AppLockState(
        enabled: enabled ?? this.enabled,
        locked: locked ?? this.locked,
        authenticating: authenticating ?? this.authenticating,
        capability: capability ?? this.capability,
        lastOutcome: clearOutcome ? null : (lastOutcome ?? this.lastOutcome),
        initialised: initialised ?? this.initialised,
      );
}

final appLockControllerProvider =
    NotifierProvider<AppLockController, AppLockState>(AppLockController.new);

/// Owns unlock-on-open: the stored preference, the lock/unlock transitions, and
/// the lifecycle rule that decides when a backgrounded app has been away long
/// enough to re-lock.
///
/// Deliberately independent of [AuthController]. Locking is not signing out —
/// the session, the sync engine and the upload queue keep running behind the
/// lock screen, because a capture queue that stops draining while the phone is
/// in someone's pocket would defeat the point of offline capture.
class AppLockController extends Notifier<AppLockState> {
  final _log = AppLogger.of('AppLock');

  DateTime? _backgroundedAt;

  BiometricService get _biometrics => ref.read(biometricServiceProvider);
  SecureStorageService get _storage => ref.read(secureStorageProvider);

  @override
  AppLockState build() => const AppLockState();

  /// Restore the preference and lock immediately if it is on.
  ///
  /// Called once at startup. Locking here rather than after the first unlock
  /// attempt means a cold start never paints the dashboard first.
  Future<void> bootstrap() async {
    final enabled = await _storage.readBiometricLockEnabled();
    final capability = await _biometrics.capability();

    // The preference can outlive the credential that backed it: a user may
    // remove every fingerprint and the device PIN after enabling this. Honouring
    // it then would show a lock screen whose only button cannot succeed, so the
    // preference is stood down instead — the session is still protected by the
    // device itself being unlocked.
    if (enabled && !capability.isSupported) {
      _log.warning('Lock enabled but device has no credential — standing down');
      await _storage.writeBiometricLockEnabled(false);
      state = state.copyWith(
        enabled: false,
        capability: capability,
        initialised: true,
      );
      return;
    }

    state = state.copyWith(
      enabled: enabled,
      locked: enabled,
      capability: capability,
      initialised: true,
    );
  }

  /// Turn the feature on or off. Enabling prompts first: a toggle that flips
  /// without proving the prompt works would lock the user out on next launch.
  /// Returns the outcome so the caller can explain a refusal.
  Future<UnlockOutcome> setEnabled(bool enabled) async {
    if (!enabled) {
      await _storage.writeBiometricLockEnabled(false);
      state = state.copyWith(enabled: false, locked: false, clearOutcome: true);
      return UnlockOutcome.success;
    }

    final capability = await _biometrics.capability();
    if (!capability.isSupported) {
      state = state.copyWith(
        capability: capability,
        lastOutcome: UnlockOutcome.unavailable,
      );
      return UnlockOutcome.unavailable;
    }

    final outcome = await _biometrics.authenticate(
      reason: 'Confirm it is you to turn on unlock for Axythic',
    );
    if (outcome == UnlockOutcome.success) {
      await _storage.writeBiometricLockEnabled(true);
      state = state.copyWith(
        enabled: true,
        capability: capability,
        lastOutcome: outcome,
      );
    } else {
      state = state.copyWith(capability: capability, lastOutcome: outcome);
    }
    return outcome;
  }

  /// Run the unlock prompt. No-op while one is already on screen.
  Future<void> unlock() async {
    if (state.authenticating || !state.locked) return;

    state = state.copyWith(authenticating: true, clearOutcome: true);
    final outcome = await _biometrics.authenticate(
      reason: 'Unlock Axythic',
    );

    if (outcome == UnlockOutcome.success) {
      _backgroundedAt = null;
      state = state.copyWith(
        locked: false,
        authenticating: false,
        lastOutcome: outcome,
      );
      return;
    }

    // A device that can no longer authenticate must not hold the app hostage.
    // Standing the preference down leaves the user in their session rather than
    // forcing a sign-out they may have no signal to undo.
    if (outcome == UnlockOutcome.unavailable) {
      _log.warning('Credential disappeared while locked — standing down');
      await _storage.writeBiometricLockEnabled(false);
      state = state.copyWith(
        enabled: false,
        locked: false,
        authenticating: false,
        lastOutcome: outcome,
      );
      return;
    }

    state = state.copyWith(authenticating: false, lastOutcome: outcome);
  }

  /// Lock now, regardless of the grace period. Used by the More screen's
  /// "Lock now" action.
  void lock() {
    if (!state.enabled) return;
    state = state.copyWith(locked: true, clearOutcome: true);
  }

  /// Lifecycle hook. [now] is injected so the grace period is testable without
  /// waiting on a wall clock.
  void onLifecycleChange(AppLifecycleState lifecycle, {DateTime? now}) {
    if (!state.enabled) return;
    final at = now ?? DateTime.now();

    switch (lifecycle) {
      case AppLifecycleState.paused:
      case AppLifecycleState.detached:
      case AppLifecycleState.hidden:
        // Only the first background stamp counts. iOS emits inactive→hidden→
        // paused on the way out; restamping on each would keep pushing the
        // deadline forward and the app would never re-lock.
        _backgroundedAt ??= at;
      case AppLifecycleState.resumed:
        final since = _backgroundedAt;
        _backgroundedAt = null;
        if (since == null || state.locked) return;
        if (at.difference(since) >= kAppLockGracePeriod) {
          state = state.copyWith(locked: true, clearOutcome: true);
        }
      case AppLifecycleState.inactive:
        // Deliberately ignored. iOS reports `inactive` for a notification
        // shade pull or an incoming call banner, neither of which is leaving
        // the app; treating it as backgrounding would re-lock constantly.
        break;
    }
  }
}
