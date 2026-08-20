import 'package:flutter/services.dart';
import 'package:local_auth/error_codes.dart' as auth_error;
import 'package:local_auth/local_auth.dart';

import 'package:nexora_mobile/core/services/app_logger.dart';

/// Why an unlock attempt ended the way it did.
///
/// A plain bool would collapse three situations that need different handling: a
/// user who tapped Cancel is still at the lock screen and can try again, a
/// device with nothing enrolled can never succeed and must not be asked, and a
/// device locked out after too many failures needs the user to wait rather than
/// keep tapping.
enum UnlockOutcome {
  /// Identity confirmed — biometric or device credential.
  success,

  /// The user dismissed the prompt. Not an error; do not report it as one.
  cancelled,

  /// The prompt ran and rejected the attempt.
  failed,

  /// No biometric enrolled and no device passcode set, or no hardware at all.
  /// Nothing the user does at the lock screen can fix this.
  unavailable,

  /// Too many failed attempts; the platform has temporarily (or permanently)
  /// disabled the prompt.
  lockedOut,

  /// The plugin threw something we do not have a mapping for.
  error,
}

/// What kind of credential this device can actually verify.
class BiometricCapability {
  const BiometricCapability({
    required this.hasBiometrics,
    required this.hasDeviceCredential,
    required this.types,
  });

  const BiometricCapability.none()
      : hasBiometrics = false,
        hasDeviceCredential = false,
        types = const [];

  /// A fingerprint / face / iris is enrolled.
  final bool hasBiometrics;

  /// The device has *some* verifiable credential — a PIN, pattern or passcode
  /// counts. This is what makes the feature offerable at all.
  final bool hasDeviceCredential;

  final List<BiometricType> types;

  bool get isSupported => hasDeviceCredential;

  /// User-facing name for whatever this device would actually prompt with.
  /// Android reports `strong`/`weak` rather than the modality, so those fall
  /// back to the generic word rather than guessing "fingerprint" on a
  /// face-unlock phone.
  String get label {
    if (!hasBiometrics) return 'Device PIN';
    if (types.contains(BiometricType.face)) return 'Face unlock';
    if (types.contains(BiometricType.fingerprint)) return 'Fingerprint';
    if (types.contains(BiometricType.iris)) return 'Iris';
    return 'Biometrics';
  }
}

/// Wraps `local_auth` behind a surface that never throws at the caller.
///
/// Every failure mode here is one the UI has to render rather than crash on: a
/// user standing at a counter with a locked app needs a sentence and a way
/// forward, not an exception.
class BiometricService {
  BiometricService([LocalAuthentication? auth])
      : _auth = auth ?? LocalAuthentication();

  final LocalAuthentication _auth;
  final _log = AppLogger.of('BiometricService');

  /// What this device can verify. Never throws — a device that cannot answer
  /// is treated as one that cannot authenticate.
  Future<BiometricCapability> capability() async {
    try {
      // isDeviceSupported() is true when *any* credential is set, biometric or
      // not. That is the real gate: the unlock prompt falls back to the device
      // PIN, so a phone with a passcode and no enrolled finger still works.
      final supported = await _auth.isDeviceSupported();
      if (!supported) return const BiometricCapability.none();

      final canCheck = await _auth.canCheckBiometrics;
      final types = canCheck ? await _auth.getAvailableBiometrics() : const [];

      return BiometricCapability(
        hasBiometrics: canCheck && types.isNotEmpty,
        hasDeviceCredential: true,
        types: List<BiometricType>.from(types),
      );
    } on PlatformException catch (e) {
      _log.warning('Could not read biometric capability: ${e.code}');
      return const BiometricCapability.none();
    }
  }

  /// Prompt for identity. [reason] is shown by the OS on iOS and in the
  /// Android prompt subtitle, so it must say what is being unlocked.
  Future<UnlockOutcome> authenticate({required String reason}) async {
    try {
      final ok = await _auth.authenticate(
        localizedReason: reason,
        options: const AuthenticationOptions(
          // Device credential stays allowed on purpose. biometricOnly: true
          // would mean a user who cuts a finger, or whose sensor fails, is
          // locked out of a session they legitimately hold — and the only exit
          // would be signing out and re-authenticating against a server they
          // may have no signal to reach.
          biometricOnly: false,
          // Keep the prompt up across an app switch (e.g. the system's own
          // credential sheet) instead of silently cancelling.
          stickyAuth: true,
          useErrorDialogs: true,
        ),
      );
      return ok ? UnlockOutcome.success : UnlockOutcome.cancelled;
    } on PlatformException catch (e) {
      return _mapError(e);
    }
  }

  UnlockOutcome _mapError(PlatformException e) {
    switch (e.code) {
      case auth_error.notAvailable:
      case auth_error.notEnrolled:
      case auth_error.passcodeNotSet:
        _log.warning('Unlock unavailable: ${e.code}');
        return UnlockOutcome.unavailable;
      case auth_error.lockedOut:
      case auth_error.permanentlyLockedOut:
        return UnlockOutcome.lockedOut;
      default:
        _log.severe('Unlock failed: ${e.code} ${e.message}');
        return UnlockOutcome.error;
    }
  }
}
