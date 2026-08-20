import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:nexora_mobile/core/di/capture_providers.dart';
import 'package:nexora_mobile/core/di/outbox_providers.dart';
import 'package:nexora_mobile/core/config/app_environment.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/observability/crash_reporter.dart';
import 'package:nexora_mobile/core/outbox/outbox_repository.dart';
import 'package:nexora_mobile/core/router/app_routes.dart';
import 'package:nexora_mobile/core/security/presentation/app_lock_tile.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';

/// Everything about how this device behaves, in one place.
///
/// Split out of the More tab rather than appended to it: More had grown long
/// enough that Sign out sat below the fold, and the answer to that is grouping,
/// not another row.
///
/// There is deliberately no theme control. The product is dark-only by
/// decision, so a toggle would be a switch that does nothing — worse than its
/// absence, because it invites a bug report.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final config = ref.watch(appConfigProvider);
    final pending = ref.watch(outboxOutstandingProvider);

    final outstanding = pending.valueOrNull ?? const [];
    final stuck = outstanding
        .where((e) => e.parsedStatus == OutboxStatus.deadLetter)
        .length;

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          const SectionHeader(
            title: 'YOUR CHANGES',
            icon: Icons.cloud_upload_outlined,
          ),
          ActionTile(
            title: 'Pending changes',
            subtitle: _pendingSubtitle(outstanding.length, stuck),
            icon: outstanding.isEmpty
                ? Icons.cloud_done_outlined
                : Icons.cloud_upload_rounded,
            color: stuck > 0
                ? AppColors.danger
                : (outstanding.isEmpty ? AppColors.success : AppColors.warning),
            onTap: () => context.go(AppRoutes.pendingChangesFullPath),
          ),
          const SizedBox(height: 20),
          const SectionHeader(
            title: 'SECURITY',
            icon: Icons.shield_outlined,
          ),
          const AppLockTile(),
          const SizedBox(height: 20),
          const SectionHeader(
            title: 'SERVER',
            icon: Icons.dns_outlined,
          ),
          _ReadOnlyTile(
            title: 'Backend',
            value: config.apiBaseUrl,
            icon: Icons.link_rounded,
            // Cleartext is worth naming rather than hiding: on this connection
            // the session token is readable by anything on the path, and a
            // release build cannot use it at all.
            warning:
                config.isCleartext ? 'Not encrypted — development only' : null,
          ),
          _ReadOnlyTile(
            title: 'Environment',
            value: config.environment.label,
            icon: Icons.layers_outlined,
          ),
          const SizedBox(height: 20),
          const SectionHeader(
            title: 'STORAGE',
            icon: Icons.sd_storage_outlined,
          ),
          ActionTile(
            title: 'Free up space',
            subtitle: 'Delete page images of invoices already exported',
            icon: Icons.cleaning_services_outlined,
            onTap: () => _freeSpace(context, ref),
          ),
          const SizedBox(height: 20),
          const SectionHeader(
            title: 'DIAGNOSTICS',
            icon: Icons.bug_report_outlined,
          ),
          ActionTile(
            title: 'Device Status',
            subtitle: 'Identity, connectivity and backend health',
            icon: Icons.smartphone_outlined,
            onTap: () => context.go(AppRoutes.deviceStatusFullPath),
          ),
          ActionTile(
            title: 'Configuration Status',
            subtitle: 'Store configuration cached on this device',
            icon: Icons.settings_ethernet_rounded,
            onTap: () => context.go(AppRoutes.configurationStatusFullPath),
          ),
          ActionTile(
            title: 'Agent Settings',
            subtitle: 'Sync interval, logging and diagnostics',
            icon: Icons.tune_rounded,
            onTap: () => context.go(AppRoutes.agentSettingsFullPath),
          ),
          const _RecentErrorsTile(),
        ],
      ),
    );
  }

  String _pendingSubtitle(int total, int stuck) {
    if (total == 0) return 'Everything is synced';
    if (stuck > 0) {
      return '$stuck of $total need your attention';
    }
    return '$total waiting to be sent';
  }

  Future<void> _freeSpace(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    final removed =
        await ref.read(captureQueueRepositoryProvider).pruneExportedImages();
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          removed == 0
              ? 'Nothing to clear — no exported invoices are still holding '
                  'images.'
              : 'Cleared $removed page image${removed == 1 ? '' : 's'}.',
        ),
      ),
    );
  }
}

class _ReadOnlyTile extends StatelessWidget {
  const _ReadOnlyTile({
    required this.title,
    required this.value,
    required this.icon,
    this.warning,
  });

  final String title;
  final String value;
  final IconData icon;
  final String? warning;

  @override
  Widget build(BuildContext context) {
    return ActionTile(
      title: title,
      subtitle: warning == null ? value : '$value  ·  $warning',
      icon: icon,
      color: warning == null ? AppColors.accent : AppColors.warning,
      trailing: const SizedBox.shrink(),
    );
  }
}

/// Recent crashes, read from the in-memory reporter.
///
/// With no server-side crash record, this is the way a store user's "it closed
/// on me" becomes something actionable.
class _RecentErrorsTile extends ConsumerWidget {
  const _RecentErrorsTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final reporter = ref.watch(crashReporterProvider);
    final recent =
        reporter is LoggingCrashReporter ? reporter.recent : <CrashRecord>[];

    return ActionTile(
      title: 'Recent errors',
      subtitle: recent.isEmpty
          ? 'None since the app started'
          : '${recent.length} since the app started',
      icon: Icons.report_outlined,
      color: recent.isEmpty ? AppColors.textMuted : AppColors.warning,
      onTap: recent.isEmpty
          ? null
          : () => showModalBottomSheet<void>(
                context: context,
                showDragHandle: true,
                isScrollControlled: true,
                builder: (_) => _ErrorsSheet(records: recent),
              ),
    );
  }
}

class _ErrorsSheet extends StatelessWidget {
  const _ErrorsSheet({required this.records});

  final List<CrashRecord> records;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.7,
        ),
        child: ListView.separated(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
          itemCount: records.length,
          separatorBuilder: (_, __) => const Divider(height: 20),
          itemBuilder: (_, i) {
            final record = records[i];
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        record.summary,
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                    ),
                    if (record.fatal)
                      const StatusBadge(
                        label: 'Fatal',
                        color: AppColors.danger,
                        dense: true,
                      ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  '${record.context ?? 'app'} · ${record.at}',
                  style: const TextStyle(
                    fontSize: 11.5,
                    color: AppColors.textMuted,
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}
