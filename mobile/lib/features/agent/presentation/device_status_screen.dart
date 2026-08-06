import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/agent_providers.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/agent/presentation/widgets/agent_health_card.dart';
import 'package:nexora_mobile/features/agent/presentation/widgets/status_widgets.dart';

/// Phase 2 — device registration + backend health / API compatibility,
/// led by a single health hero card with device identity below it.
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
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              AgentHealthCard(state: state),
              const SizedBox(height: 16),
              const SectionHeader(
                  title: 'THIS DEVICE', icon: Icons.smartphone_outlined,),
              device.when(
                loading: () => const InlineLoading(),
                error: (e, _) => Text('$e'),
                data: (id) => StatusCard(
                  accentColor: AppColors.line,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          InfoChip(
                              label: id?.platform ?? '—',
                              icon: Icons.devices_other_rounded,),
                          InfoChip(
                              label: _orDash(id?.model) ?? 'Unknown model',
                              icon: Icons.phone_android_rounded,),
                          InfoChip(
                              label: id?.versionLabel ?? '—',
                              icon: Icons.info_outline_rounded,),
                        ],
                      ),
                      const SizedBox(height: 4),
                      const Divider(height: 24),
                      InfoRow(label: 'Device ID', value: id?.deviceId),
                      InfoRow(label: 'OS', value: _orDash(id?.osVersion)),
                      InfoRow(
                          label: 'Registered',
                          value: formatRelative(id?.registeredAt),),
                      InfoRow(
                          label: 'Last seen',
                          value: formatRelative(id?.lastSeenAt),),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

String? _orDash(String? v) => (v == null || v.isEmpty) ? null : v;
