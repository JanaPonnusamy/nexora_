import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/agent/agent_state.dart';
import 'package:nexora_mobile/core/agent/agent_status.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/agent/presentation/widgets/status_widgets.dart'
    show formatRelative;

/// One-glance health summary for the Device Status screen: agent status hero
/// plus a compact grid of pass/fail checks instead of two stacked tables of
/// label/value rows.
class AgentHealthCard extends StatelessWidget {
  const AgentHealthCard({super.key, required this.state});

  final AgentState state;

  Color get _color => switch (state.status) {
        AgentStatus.ready => AppColors.success,
        AgentStatus.degraded => AppColors.warning,
        AgentStatus.error => AppColors.error,
        AgentStatus.offline => AppColors.slate,
        _ => AppColors.primary,
      };

  IconData get _icon => switch (state.status) {
        AgentStatus.ready => Icons.verified_outlined,
        AgentStatus.degraded => Icons.warning_amber_rounded,
        AgentStatus.error => Icons.error_outline_rounded,
        AgentStatus.offline => Icons.cloud_off_rounded,
        _ => Icons.hub_outlined,
      };

  @override
  Widget build(BuildContext context) {
    final color = _color;
    return StatusCard(
      accentColor: color,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.14),
                  shape: BoxShape.circle,
                ),
                child: Icon(_icon, color: color, size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(state.status.label,
                        style: const TextStyle(
                            fontSize: 17, fontWeight: FontWeight.w800,),),
                    const SizedBox(height: 2),
                    Text(
                      state.storeName ?? 'No store bound',
                      style: const TextStyle(
                          fontSize: 12, color: AppColors.slate,),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _CheckChip(label: 'Registered', ok: state.registered),
              _CheckChip(label: 'Config loaded', ok: state.configLoaded),
              _CheckChip(label: 'Backend reachable', ok: state.backendReachable),
              _CheckChip(label: 'API compatible', ok: state.apiCompatible),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Icon(Icons.speed_rounded, size: 14, color: AppColors.slate),
              const SizedBox(width: 6),
              Text(
                state.backendLatencyMs == null
                    ? 'Latency —'
                    : 'Latency ${state.backendLatencyMs} ms',
                style: const TextStyle(fontSize: 12, color: AppColors.slate),
              ),
              const SizedBox(width: 14),
              Icon(Icons.schedule_rounded, size: 14, color: AppColors.slate),
              const SizedBox(width: 6),
              Text(
                'Checked ${formatRelative(state.lastHealthCheckAt)}',
                style: const TextStyle(fontSize: 12, color: AppColors.slate),
              ),
            ],
          ),
          if (state.lastError != null) ...[
            const SizedBox(height: 10),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.error_outline, size: 15, color: AppColors.error),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(state.lastError!,
                      style: const TextStyle(
                          fontSize: 12, color: AppColors.error,),),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _CheckChip extends StatelessWidget {
  const _CheckChip({required this.label, required this.ok});
  final String label;
  final bool ok;

  @override
  Widget build(BuildContext context) {
    final color = ok ? AppColors.success : AppColors.slate;
    return InfoChip(
      label: label,
      icon: ok ? Icons.check_circle_rounded : Icons.remove_circle_outline,
      color: color,
    );
  }
}
