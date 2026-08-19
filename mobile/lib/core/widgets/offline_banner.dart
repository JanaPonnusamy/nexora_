import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';

/// A slim bar that appears under the app bar when the device has no network.
///
/// It states what still works rather than only what is wrong. This app is built
/// to keep going offline — captures queue, suppliers read from the local cache,
/// sync resumes on reconnect — so a bare "No connection" would make users stop
/// working when they do not need to. It is the difference between a warning and
/// a reassurance, and only one of those is true here.
///
/// Deliberately not a SnackBar: a store is offline for minutes at a time, and a
/// transient toast cannot answer "is it still offline?" ten seconds later.
class OfflineBanner extends ConsumerWidget {
  const OfflineBanner({super.key, this.message});

  /// Overrides the default reassurance for a screen where offline means
  /// something more specific — Sync Live is online-only, for instance.
  final String? message;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final online = ref.watch(isOnlineProvider);

    // AnimatedSize rather than a bare conditional: the bar pushes content down,
    // and having that content jump on every tunnel and lift is worse than the
    // 180ms it costs to slide.
    return AnimatedSize(
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeOut,
      alignment: Alignment.topCenter,
      child: online
          ? const SizedBox(width: double.infinity)
          : _Bar(message: message),
    );
  }
}

class _Bar extends StatelessWidget {
  const _Bar({this.message});

  final String? message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      color: AppColors.warningSunk,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
      child: Row(
        children: [
          const Icon(
            Icons.cloud_off_rounded,
            size: 16,
            color: AppColors.warningInk,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message ?? 'Offline — your work is saved and will sync later.',
              style: const TextStyle(
                fontSize: 12.5,
                height: 1.25,
                color: AppColors.warningInk,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
