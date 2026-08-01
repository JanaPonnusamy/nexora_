import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/agent/agent_settings.dart';
import 'package:nexora_mobile/core/di/agent_providers.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/features/agent/presentation/widgets/status_widgets.dart';

/// Phase 2 — user-tunable agent runtime settings, persisted across restarts.
class AgentSettingsScreen extends ConsumerStatefulWidget {
  const AgentSettingsScreen({super.key});

  @override
  ConsumerState<AgentSettingsScreen> createState() =>
      _AgentSettingsScreenState();
}

class _AgentSettingsScreenState extends ConsumerState<AgentSettingsScreen> {
  late AgentSettings _draft;
  bool _saving = false;

  static const _syncChoices = [1, 5, 15, 30, 60, 120, 240];
  static const _healthChoices = [1, 2, 5, 15, 30, 60];

  @override
  void initState() {
    super.initState();
    _draft = ref.read(agentManagerProvider).settings;
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    await ref.read(agentManagerProvider).updateSettings(_draft);
    if (!mounted) return;
    setState(() => _saving = false);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Agent settings saved')),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Agent Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          SectionCard(
            title: 'Synchronization',
            icon: Icons.sync_rounded,
            children: [
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Automatic background sync'),
                subtitle: const Text('Sync on a schedule and on reconnect'),
                value: _draft.autoSync,
                onChanged: (v) =>
                    setState(() => _draft = _draft.copyWith(autoSync: v)),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Sync on startup'),
                subtitle: const Text('Run a sync as soon as the agent starts'),
                value: _draft.syncOnStartup,
                onChanged: (v) =>
                    setState(() => _draft = _draft.copyWith(syncOnStartup: v)),
              ),
              _MinutesDropdown(
                label: 'Sync interval',
                value: _draft.syncInterval.inMinutes,
                choices: _syncChoices,
                enabled: _draft.autoSync,
                onChanged: (m) => setState(() => _draft =
                    _draft.copyWith(syncInterval: Duration(minutes: m)),),
              ),
            ],
          ),
          const SizedBox(height: 12),
          SectionCard(
            title: 'Health & diagnostics',
            icon: Icons.monitor_heart_outlined,
            children: [
              _MinutesDropdown(
                label: 'Health check interval',
                value: _draft.healthCheckInterval.inMinutes,
                choices: _healthChoices,
                enabled: true,
                onChanged: (m) => setState(() => _draft =
                    _draft.copyWith(healthCheckInterval: Duration(minutes: m)),),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Verbose logging'),
                subtitle: const Text('Record fine-grained sync activity'),
                value: _draft.verboseLogging,
                onChanged: (v) =>
                    setState(() => _draft = _draft.copyWith(verboseLogging: v)),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.all(8),
            child: Text(
              'The backend address is set at build time and is not editable '
              'here. No credentials are stored on the device.',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: AppColors.slate),
            ),
          ),
          const SizedBox(height: 8),
          FilledButton.icon(
            onPressed: _saving ? null : _save,
            icon: _saving
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(
                        strokeWidth: 2.2, color: Colors.white,),
                  )
                : const Icon(Icons.save_outlined),
            label: Text(_saving ? 'Saving…' : 'Save settings'),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

class _MinutesDropdown extends StatelessWidget {
  const _MinutesDropdown({
    required this.label,
    required this.value,
    required this.choices,
    required this.onChanged,
    required this.enabled,
  });

  final String label;
  final int value;
  final List<int> choices;
  final ValueChanged<int> onChanged;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    // Guard against a persisted value that isn't one of the presets.
    final items = {...choices, value}.toList()..sort();
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(color: enabled ? null : AppColors.slate),
            ),
          ),
          DropdownButton<int>(
            value: value,
            onChanged: enabled ? (v) => v == null ? null : onChanged(v) : null,
            items: [
              for (final m in items)
                DropdownMenuItem(
                  value: m,
                  child: Text(m == 1 ? '1 min' : '$m min'),
                ),
            ],
          ),
        ],
      ),
    );
  }
}
