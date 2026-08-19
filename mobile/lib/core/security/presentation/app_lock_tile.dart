import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/security/app_lock_controller.dart';
import 'package:nexora_mobile/core/security/biometric_service.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';

/// The switch that turns unlock-on-open on and off.
///
/// Opt-in rather than mandatory: a phone with no enrolled credential cannot
/// satisfy a mandatory lock at all, and the people using this app are on a shop
/// floor with gloves and wet hands as often as not. Making it a choice is also
/// what the Settings spec assumes.
class AppLockTile extends ConsumerWidget {
  const AppLockTile({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(appLockControllerProvider);

    // Offering a toggle that cannot be turned on is worse than not offering it:
    // it reads as a broken feature rather than an unmet device requirement.
    if (state.initialised && !state.capability.isSupported) {
      return const ActionTile(
        title: 'Unlock on open',
        subtitle: 'Set a screen lock on this device to use this',
        icon: Icons.lock_outline_rounded,
        color: AppColors.textMuted,
        trailing: SizedBox.shrink(),
      );
    }

    return ActionTile(
      title: 'Unlock on open',
      subtitle: state.enabled
          ? 'Ask for ${state.capability.label} when reopening Axythic'
          : 'Anyone holding this phone can open Axythic',
      icon: state.enabled ? Icons.lock_rounded : Icons.lock_open_rounded,
      color: state.enabled ? AppColors.success : AppColors.warning,
      trailing: Switch(
        value: state.enabled,
        onChanged: state.initialised ? (v) => _toggle(context, ref, v) : null,
      ),
      onTap: state.initialised
          ? () => _toggle(context, ref, !state.enabled)
          : null,
    );
  }

  Future<void> _toggle(BuildContext context, WidgetRef ref, bool next) async {
    final messenger = ScaffoldMessenger.of(context);
    final outcome =
        await ref.read(appLockControllerProvider.notifier).setEnabled(next);

    // A cancelled prompt is the user changing their mind, not a failure — the
    // switch simply stays where it was and nothing is said about it.
    if (outcome == UnlockOutcome.success ||
        outcome == UnlockOutcome.cancelled) {
      return;
    }

    messenger.showSnackBar(
      SnackBar(
        content: Text(
          switch (outcome) {
            UnlockOutcome.unavailable =>
              'This device has no fingerprint, face unlock or PIN set up yet.',
            UnlockOutcome.lockedOut =>
              'Too many attempts. Your device paused unlocking — try again in '
                  'a moment.',
            _ => 'Could not turn this on. Unlocking is not working on this '
                'device.',
          },
        ),
      ),
    );
  }
}
