import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/agent/agent_state.dart';
import 'package:nexora_mobile/core/agent/agent_status.dart';
import 'package:nexora_mobile/core/di/agent_providers.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/features/agent/presentation/widgets/status_widgets.dart';

/// Phase 2 — device registration + backend health / API compatibility.
class DeviceStatusScreen extends ConsumerWidget {
  const DeviceStatusScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final agentAsync = ref.watch(agentStateProvider);
    final device = ref.watch(cachedDeviceProvider);
    final agent = ref.read(agentManagerProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Device Status')),
      body: agentAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Agent unavailable: $e')),
        data: (state) => RefreshIndicator(
          onRefresh: () async {
            await agent.refreshConfiguration();
            ref.invalidate(cachedDeviceProvider);
          },
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _AgentCard(state: state),
              const SizedBox(height: 12),
              _ConnectivityCard(state: state),
              const SizedBox(height: 12),
              device.when(
                loading: () => const SizedBox.shrink(),
                error: (e, _) => Text('$e'),
                data: (id) => SectionCard(
                  title: 'Device',
                  icon: Icons.smartphone_outlined,
                  children: [
                    InfoRow(label: 'Device ID', value: id?.deviceId),
                    InfoRow(label: 'Platform', value: id?.platform),
                    InfoRow(label: 'Model', value: _orDash(id?.model)),
                    InfoRow(label: 'OS', value: _orDash(id?.osVersion)),
                    InfoRow(label: 'App version', value: id?.versionLabel),
                    InfoRow(
                        label: 'Registered',
                        value: formatRelative(id?.registeredAt),),
                    InfoRow(
                        label: 'Last seen',
                        value: formatRelative(id?.lastSeenAt),),
                  ],
                ),
              ),
              const SizedBox(height: 24),
            ],
          ),
        ),
      ),
    );
  }
}

String? _orDash(String? v) => (v == null || v.isEmpty) ? null : v;

Color _agentColor(AgentStatus s) => switch (s) {
      AgentStatus.ready => AppColors.success,
      AgentStatus.degraded => AppColors.warning,
      AgentStatus.error => AppColors.error,
      AgentStatus.offline => AppColors.slate,
      _ => AppColors.primary,
    };

class _AgentCard extends StatelessWidget {
  const _AgentCard({required this.state});
  final AgentState state;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      title: 'Store Agent',
      icon: Icons.hub_outlined,
      trailing: StatusPill(
          label: state.status.label, color: _agentColor(state.status),),
      children: [
        InfoRow(
          label: 'Device registered',
          valueWidget: _BoolPill(value: state.registered),
        ),
        InfoRow(
          label: 'Configuration loaded',
          valueWidget: _BoolPill(value: state.configLoaded),
        ),
        InfoRow(label: 'Active store', value: state.storeName),
        if (state.lastError != null)
          InfoRow(label: 'Last error', value: state.lastError),
      ],
    );
  }
}

class _ConnectivityCard extends StatelessWidget {
  const _ConnectivityCard({required this.state});
  final AgentState state;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      title: 'Backend connectivity',
      icon: Icons.cloud_outlined,
      children: [
        InfoRow(
          label: 'Reachable',
          valueWidget: _BoolPill(value: state.backendReachable),
        ),
        InfoRow(
          label: 'API compatible',
          valueWidget: _BoolPill(value: state.apiCompatible),
        ),
        InfoRow(
          label: 'Latency',
          value: state.backendLatencyMs == null
              ? '—'
              : '${state.backendLatencyMs} ms',
        ),
        InfoRow(
          label: 'Server API version',
          value: state.serverApiVersion ?? 'Not advertised',
        ),
        InfoRow(
          label: 'Last checked',
          value: formatRelative(state.lastHealthCheckAt),
        ),
      ],
    );
  }
}

class _BoolPill extends StatelessWidget {
  const _BoolPill({required this.value});
  final bool value;

  @override
  Widget build(BuildContext context) => StatusPill(
        label: value ? 'Yes' : 'No',
        color: value ? AppColors.success : AppColors.slate,
        icon: value ? Icons.check_circle_outline : Icons.remove_circle_outline,
      );
}
