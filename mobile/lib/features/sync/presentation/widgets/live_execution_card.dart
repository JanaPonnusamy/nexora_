import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/sync/data/sync_live_models.dart';

/// One store's in-flight sync.
///
/// The bar tracks the **whole execution**, not the current table: a per-table
/// bar restarts at zero on every table, which reads as the sync going
/// backwards. The table is named underneath so the detail is still there.
class LiveExecutionCard extends StatelessWidget {
  const LiveExecutionCard({
    super.key,
    required this.execution,
    required this.onControl,
    this.busy = false,
  });

  final LiveSyncExecution execution;
  final void Function(SyncControlAction action) onControl;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final paused = execution.isPaused;
    final tone = paused ? AppColors.warning : AppColors.info;
    final progress = execution.executionProgress;

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: StatusCard(
        accentColor: tone,
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    execution.label,
                    style: const TextStyle(
                      fontSize: 14.5,
                      fontWeight: FontWeight.w700,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                StatusBadge(
                  label: paused ? 'Paused' : 'Syncing',
                  color: tone,
                  icon: paused ? Icons.pause_rounded : Icons.sync_rounded,
                  dense: true,
                ),
              ],
            ),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                // Null keeps the bar indeterminate until the agent reports
                // totals. A 0% bar would claim progress information the
                // server has not actually sent yet.
                value: progress,
                minHeight: 6,
                backgroundColor: tone.withValues(alpha: 0.12),
                valueColor: AlwaysStoppedAnimation(tone),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              _progressLine(),
              style: const TextStyle(
                fontSize: 12,
                color: AppColors.textSoft,
              ),
            ),
            if (execution.currentTable != null)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: [
                    InfoChip(
                      label: execution.currentTable!,
                      icon: Icons.table_rows_outlined,
                      color: AppColors.accentInk,
                    ),
                    if (execution.syncType != null)
                      InfoChip(
                        label: execution.syncType!,
                        icon: Icons.swap_vert_rounded,
                      ),
                    if (execution.speedRowsSec > 0)
                      InfoChip(
                        label: '${execution.speedRowsSec.toStringAsFixed(0)}'
                            ' rows/s',
                        icon: Icons.speed_rounded,
                      ),
                    if (execution.eta != null)
                      InfoChip(
                        label: 'ETA ${_short(execution.eta!)}',
                        icon: Icons.timer_outlined,
                      ),
                  ],
                ),
              ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              children: [
                if (!paused)
                  _ControlButton(
                    label: 'Pause',
                    icon: Icons.pause_rounded,
                    color: AppColors.warning,
                    onPressed:
                        busy ? null : () => onControl(SyncControlAction.pause),
                  ),
                _ControlButton(
                  label: 'Stop',
                  icon: Icons.stop_rounded,
                  color: AppColors.danger,
                  onPressed:
                      busy ? null : () => onControl(SyncControlAction.stop),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _progressLine() {
    final done = execution.executionRowsProcessed;
    final total = execution.executionTotalRows;
    final elapsed = execution.elapsed;

    final rows = total == null
        ? '${_compact(done)} rows sent'
        : '${_compact(done)} of ${_compact(total)} rows';
    final pct = execution.executionProgress;
    final pctText = pct == null ? '' : ' · ${(pct * 100).round()}%';
    final forText = elapsed == null ? '' : ' · ${_short(elapsed)} elapsed';
    return '$rows$pctText$forText';
  }

  static String _compact(int n) {
    if (n < 1000) return '$n';
    if (n < 1000000) return '${(n / 1000).toStringAsFixed(n < 10000 ? 1 : 0)}k';
    return '${(n / 1000000).toStringAsFixed(1)}M';
  }

  static String _short(Duration d) {
    if (d.inSeconds < 60) return '${d.inSeconds}s';
    if (d.inMinutes < 60) return '${d.inMinutes}m';
    return '${d.inHours}h ${d.inMinutes.remainder(60)}m';
  }
}

/// Explicit `minimumSize` — the app theme gives buttons an infinite minimum
/// width, which asserts inside a Wrap. See §3.8 in the mobile handoff.
class _ControlButton extends StatelessWidget {
  const _ControlButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.onPressed,
  });

  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return TextButton.icon(
      onPressed: onPressed,
      icon: Icon(icon, size: 16),
      label: Text(label),
      style: TextButton.styleFrom(
        foregroundColor: color,
        minimumSize: const Size(0, 38),
        padding: const EdgeInsets.symmetric(horizontal: 14),
        textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
    );
  }
}
