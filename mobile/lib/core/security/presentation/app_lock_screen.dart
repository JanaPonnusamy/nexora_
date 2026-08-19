import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:local_auth/local_auth.dart' show BiometricType;

import 'package:nexora_mobile/core/security/app_lock_controller.dart';
import 'package:nexora_mobile/core/security/biometric_service.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';

/// The surface that covers the app while it is locked.
///
/// It always offers two ways forward: try again, and sign out. The second one
/// matters more than it looks — without it, a user whose fingerprint stops
/// being recognised has an app they cannot enter and cannot leave.
class AppLockScreen extends ConsumerStatefulWidget {
  const AppLockScreen({super.key});

  @override
  ConsumerState<AppLockScreen> createState() => _AppLockScreenState();
}

class _AppLockScreenState extends ConsumerState<AppLockScreen> {
  @override
  void initState() {
    super.initState();
    // Prompt without being asked: an unlock screen whose first action is
    // "tap here to be asked to unlock" is a step nobody wants.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(appLockControllerProvider.notifier).unlock();
    });
  }

  Future<void> _signOut() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Sign out?'),
        content: const Text(
          'You will need your username and password, and a connection to the '
          'server, to sign back in.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Sign out'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    await ref.read(authControllerProvider.notifier).logout();
    // Signing out ends the reason to be locked; leaving it set would put the
    // lock screen over the login screen.
    ref.read(appLockControllerProvider.notifier).lock();
    await ref.read(appLockControllerProvider.notifier).setEnabled(false);
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(appLockControllerProvider);
    final theme = Theme.of(context);

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Spacer(),
              Container(
                height: 76,
                width: 76,
                decoration: BoxDecoration(
                  color: AppColors.accentSunk,
                  borderRadius: BorderRadius.circular(22),
                ),
                alignment: Alignment.center,
                child: const Icon(
                  Icons.lock_rounded,
                  size: 34,
                  color: AppColors.accentInk,
                ),
              ),
              const SizedBox(height: 24),
              Text(
                'Axythic is locked',
                style: theme.textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 10),
              Text(
                _message(state),
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium
                    ?.copyWith(color: AppColors.textSoft),
              ),
              const SizedBox(height: 28),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: state.authenticating
                      ? null
                      : () =>
                          ref.read(appLockControllerProvider.notifier).unlock(),
                  icon: Icon(_icon(state.capability)),
                  label: Text('Unlock with ${state.capability.label}'),
                ),
              ),
              const Spacer(),
              TextButton(
                onPressed: state.authenticating ? null : _signOut,
                child: const Text('Sign out instead'),
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }

  IconData _icon(BiometricCapability capability) {
    if (!capability.hasBiometrics) return Icons.pin_rounded;
    if (capability.types.contains(BiometricType.face)) {
      return Icons.face_rounded;
    }
    return Icons.fingerprint_rounded;
  }

  /// Says what happened, in the terms the person holding the phone experienced.
  /// A cancelled prompt is not an error and is not reported as one.
  String _message(AppLockState state) => switch (state.lastOutcome) {
        UnlockOutcome.failed =>
          'That was not recognised. Try again, or use your device PIN.',
        UnlockOutcome.lockedOut =>
          'Too many attempts. Your device has paused unlocking for a while — '
              'wait a moment, or sign out and sign back in.',
        UnlockOutcome.unavailable =>
          'This device can no longer verify you. Sign out to continue.',
        UnlockOutcome.error =>
          'Unlocking did not work on this device. Sign out to continue.',
        _ => 'Confirm it is you to get back to your work. Nothing was lost — '
            'uploads and sync kept running.',
      };
}
