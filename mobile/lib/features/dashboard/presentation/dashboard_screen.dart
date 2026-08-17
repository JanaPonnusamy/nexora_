import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:nexora_mobile/core/router/app_routes.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/dashboard/application/dashboard_providers.dart';
import 'package:nexora_mobile/features/dashboard/data/dashboard_summary.dart';

/// Home tab: the at-a-glance state of the active store.
///
/// Backed by a single aggregate call (`GET /api/mobile/v1/dashboard`) rather
/// than one request per card. Sections the server could not build come back
/// null and are simply not rendered.
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authControllerProvider);
    final summary = ref.watch(dashboardSummaryProvider);

    return Scaffold(
      // Store switching and sign-out live in the More tab, so this stays
      // focused on status rather than session chrome.
      appBar: AppBar(title: const Text('Axythic')),
      body: RefreshIndicator(
        onRefresh: () async => ref.refresh(dashboardSummaryProvider.future),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
          children: [
            _Greeting(
              name: auth.user?.displayName ?? '',
              storeName: auth.selectedStore?.storeName,
            ),
            const SizedBox(height: 16),
            summary.when(
              loading: () => const _LoadingCards(),
              error: (error, _) => _DashboardError(
                message: '$error',
                onRetry: () => ref.invalidate(dashboardSummaryProvider),
              ),
              data: (data) => _Sections(summary: data),
            ),
          ],
        ),
      ),
    );
  }
}

class _Greeting extends StatelessWidget {
  const _Greeting({required this.name, this.storeName});

  final String name;
  final String? storeName;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          name.isEmpty ? 'Welcome' : 'Hi $name',
          style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 2),
        Text(
          storeName ?? 'No store selected',
          style: const TextStyle(fontSize: 14, color: AppColors.textMuted),
        ),
      ],
    );
  }
}

class _Sections extends StatelessWidget {
  const _Sections({required this.summary});

  final DashboardSummary summary;

  @override
  Widget build(BuildContext context) {
    final store = summary.store;
    final sync = summary.sync;
    final documents = summary.documents;
    final procurement = summary.procurement;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (store != null) _StoreCard(store: store),
        if (sync != null) ...[
          const SizedBox(height: 20),
          const SectionHeader(title: 'SYNC', icon: Icons.sync_rounded),
          MetricRow(
            tiles: [
              MetricTile(
                label: 'Online',
                value: '${sync.storesOnline}',
                icon: Icons.cloud_done_outlined,
                color: AppColors.success,
              ),
              MetricTile(
                label: 'Offline',
                value: '${sync.storesOffline}',
                icon: Icons.cloud_off_outlined,
                color: sync.storesOffline > 0
                    ? AppColors.warning
                    : AppColors.textMuted,
              ),
              MetricTile(
                label: 'Running',
                value: '${sync.runningForStore}',
                icon: Icons.autorenew_rounded,
                color: AppColors.info,
              ),
            ],
          ),
        ],
        if (documents != null) ...[
          const SizedBox(height: 20),
          const SectionHeader(
            title: 'DOCUMENTS',
            icon: Icons.document_scanner_outlined,
          ),
          MetricRow(
            tiles: [
              MetricTile(
                label: 'To review',
                value: '${documents.awaitingReview}',
                icon: Icons.rate_review_outlined,
                color: documents.awaitingReview > 0
                    ? AppColors.accent
                    : AppColors.textMuted,
              ),
              MetricTile(
                label: 'Processing',
                value: '${documents.processing}',
                icon: Icons.hourglass_empty_rounded,
                color: AppColors.info,
              ),
              MetricTile(
                label: 'Failed',
                value: '${documents.failed}',
                icon: Icons.error_outline_rounded,
                color: documents.failed > 0
                    ? AppColors.danger
                    : AppColors.textMuted,
              ),
            ],
          ),
        ],
        if (procurement != null) ...[
          const SizedBox(height: 20),
          const SectionHeader(
            title: 'PROCUREMENT',
            icon: Icons.inventory_2_outlined,
          ),
          if (procurement.hasActiveCycle)
            ActionTile(
              title: 'Cycle ${procurement.cycleNo}',
              subtitle: '${procurement.cycleStatus ?? 'OPEN'} · '
                  '${procurement.pendingReview} awaiting review',
              icon: Icons.autorenew_rounded,
              onTap: () => context.go(AppRoutes.procurePath),
            )
          else
            const EmptyState(
              icon: Icons.inbox_outlined,
              message: 'No open cycle for this store',
            ),
        ],
        const SizedBox(height: 20),
        const SectionHeader(title: 'SYSTEM', icon: Icons.settings_outlined),
        ActionTile(
          title: 'Device Status',
          subtitle: 'Identity, connectivity and backend health',
          icon: Icons.smartphone_outlined,
          // `go`, not `push`: these screens belong to the More branch, so this
          // crosses tabs rather than stacking onto Home.
          onTap: () => context.go(AppRoutes.deviceStatusFullPath),
        ),
        ActionTile(
          title: 'Configuration Status',
          subtitle: 'Store configuration cached on this device',
          icon: Icons.settings_ethernet_rounded,
          onTap: () => context.go(AppRoutes.configurationStatusFullPath),
        ),
      ],
    );
  }
}

class _StoreCard extends StatelessWidget {
  const _StoreCard({required this.store});

  final DashboardStore store;

  @override
  Widget build(BuildContext context) {
    final online = store.agentOnline;
    return StatusCard(
      accentColor: online ? AppColors.success : AppColors.textMuted,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  store.storeName,
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              StatusBadge(
                label: online ? 'Agent online' : 'Agent offline',
                color: online ? AppColors.success : AppColors.textMuted,
                dense: true,
              ),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              InfoChip(label: store.storeCode, icon: Icons.tag),
              if (store.lastSyncStatus != null)
                InfoChip(
                  label: store.lastSyncStatus!,
                  icon: Icons.sync_rounded,
                  color: store.lastSyncStatus == 'SUCCESS'
                      ? AppColors.success
                      : AppColors.warning,
                ),
              if (store.agentVersion != null)
                InfoChip(label: 'v${store.agentVersion}'),
            ],
          ),
        ],
      ),
    );
  }
}

class _LoadingCards extends StatelessWidget {
  const _LoadingCards();

  @override
  Widget build(BuildContext context) {
    // Skeletons rather than a spinner: the layout is known, so the page should
    // not jump once data lands.
    return Column(
      children: [
        for (var i = 0; i < 3; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Container(
              height: i == 0 ? 96 : 76,
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: AppColors.rule),
              ),
            ),
          ),
      ],
    );
  }
}

class _DashboardError extends StatelessWidget {
  const _DashboardError({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return StatusCard(
      accentColor: AppColors.warning,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Could not load the dashboard',
            style: TextStyle(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 4),
          Text(
            message,
            style: const TextStyle(fontSize: 12.5, color: AppColors.textMuted),
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 10),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('Retry'),
            ),
          ),
        ],
      ),
    );
  }
}
