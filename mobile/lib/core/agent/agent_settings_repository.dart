import 'package:nexora_mobile/core/agent/agent_settings.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/sync/sync_repository.dart';

/// Loads and persists [AgentSettings] in the configuration cache so they survive
/// application restarts. Backed by the `sync_configuration` table via
/// [SyncRepository].
class AgentSettingsRepository {
  AgentSettingsRepository(this._repo);

  static const String configKey = 'agent.settings';

  final SyncRepository _repo;
  final _log = AppLogger.of('AgentSettings');

  /// Returns persisted settings, or [AgentSettings.defaults] when none exist
  /// (or a stored value is corrupt).
  Future<AgentSettings> load() async {
    final row = await _repo.getConfig(configKey);
    if (row == null) return AgentSettings.defaults;
    try {
      return AgentSettings.decode(row.value);
    } catch (e) {
      _log.warning('Corrupt agent settings, using defaults: $e');
      return AgentSettings.defaults;
    }
  }

  Future<void> save(AgentSettings settings) async {
    await _repo.putConfig(configKey, settings.encode());
    _log.info('Saved agent settings');
  }
}
