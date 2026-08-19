import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/sync/sync_state.dart';
import 'package:nexora_mobile/core/sync/sync_status.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/agent/presentation/widgets/status_widgets.dart'
    show formatRelative;

/// Hero card for the Sync screen: one glance at engine status, a pulsing
/// icon while busy, and the sync progress bar. This is the first thing a
/// user sees, so it carries the most visual weight on the page.
class SyncProgressCard extends StatefulWidget {
  const SyncProgressCard({super.key, required this.state});

  final SyncState state;

  @override
  State<SyncProgressCard> createState() => _SyncProgressCardState();
}

class _SyncProgressCardState extends State<SyncProgressCard>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1100),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  Color get _color => switch (widget.state.status) {
        SyncStatus.success => AppColors.success,
        SyncStatus.failed => AppColors.danger,
        SyncStatus.offline => AppColors.textMuted,
        SyncStatus.paused => AppColors.warning,
        _ => AppColors.accent,
      };

  IconData get _icon => switch (widget.state.status) {
        SyncStatus.success => Icons.check_rounded,
        SyncStatus.failed => Icons.priority_high_rounded,
        SyncStatus.offline => Icons.cloud_off_rounded,
        SyncStatus.paused => Icons.pause_rounded,
        _ => Icons.sync_rounded,
      };

  @override
  Widget build(BuildContext context) {
    final state = widget.state;
    final busy = state.status.isBusy;
    final color = _color;

    return StatusCard(
      accentColor: color,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              AnimatedBuilder(
                animation: _pulse,
                builder: (context, child) {
                  final scale = busy ? 1 + (_pulse.value * 0.12) : 1.0;
                  return Transform.scale(scale: scale, child: child);
                },
                child: Container(
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.14),
                    shape: BoxShape.circle,
                  ),
                  child: Icon(_icon, color: color, size: 22),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    AnimatedSwitcher(
                      duration: const Duration(milliseconds: 200),
                      child: Text(
                        state.status.label,
                        key: ValueKey(state.status),
                        style: const TextStyle(
                          fontSize: 17,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      busy
                          ? (state.currentEntity ?? 'Syncing…')
                          : 'Last synced ${formatRelative(state.lastSuccessAt)}',
                      style: const TextStyle(
                          fontSize: 12, color: AppColors.textMuted),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              StatusBadge(
                dense: true,
                label: state.online ? 'Online' : 'Offline',
                color: state.online ? AppColors.success : AppColors.textMuted,
              ),
            ],
          ),
          const SizedBox(height: 14),
          ProgressRow(
            label: busy ? 'Syncing' : 'Up to date',
            value: busy ? (state.progress == 0 ? null : state.progress) : 1.0,
            trailingText: busy && state.progress > 0
                ? '${(state.progress * 100).round()}%'
                : null,
            color: color,
          ),
          const SizedBox(height: 4),
          MetricRow(
            tiles: [
              MetricTile(
                label: 'Pending',
                value: '${state.pending}',
                icon: Icons.hourglass_empty_rounded,
                color: AppColors.warning,
              ),
              MetricTile(
                label: 'Completed',
                value: '${state.completed}',
                icon: Icons.check_circle_outline_rounded,
                color: AppColors.success,
              ),
              MetricTile(
                label: 'Failed',
                value: '${state.failed}',
                icon: Icons.error_outline_rounded,
                color:
                    state.failed > 0 ? AppColors.danger : AppColors.textMuted,
              ),
            ],
          ),
          if (state.lastError != null) ...[
            const SizedBox(height: 10),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.error_outline,
                    size: 15, color: AppColors.danger),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    state.lastError!,
                    style: const TextStyle(
                      fontSize: 12,
                      color: AppColors.danger,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
