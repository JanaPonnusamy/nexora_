import 'dart:convert';

/// User-tunable agent runtime settings. Persisted as JSON in the configuration
/// cache so they survive restarts. Nothing here is a secret and no URL/credential
/// is stored — the backend base URL stays a build-time concern (AppConfig).
class AgentSettings {
  const AgentSettings({
    this.autoSync = true,
    this.syncInterval = const Duration(minutes: 15),
    this.healthCheckInterval = const Duration(minutes: 2),
    this.verboseLogging = false,
    this.syncOnStartup = true,
  });

  final bool autoSync;
  final Duration syncInterval;
  final Duration healthCheckInterval;
  final bool verboseLogging;
  final bool syncOnStartup;

  static const AgentSettings defaults = AgentSettings();

  // Guard rails so a bad value can never wedge the engine.
  static const _minSyncMinutes = 1;
  static const _maxSyncMinutes = 240;
  static const _minHealthMinutes = 1;
  static const _maxHealthMinutes = 60;

  AgentSettings copyWith({
    bool? autoSync,
    Duration? syncInterval,
    Duration? healthCheckInterval,
    bool? verboseLogging,
    bool? syncOnStartup,
  }) {
    return AgentSettings(
      autoSync: autoSync ?? this.autoSync,
      syncInterval: _clampMinutes(
        syncInterval ?? this.syncInterval,
        _minSyncMinutes,
        _maxSyncMinutes,
      ),
      healthCheckInterval: _clampMinutes(
        healthCheckInterval ?? this.healthCheckInterval,
        _minHealthMinutes,
        _maxHealthMinutes,
      ),
      verboseLogging: verboseLogging ?? this.verboseLogging,
      syncOnStartup: syncOnStartup ?? this.syncOnStartup,
    );
  }

  Map<String, dynamic> toJson() => {
        'autoSync': autoSync,
        'syncIntervalMinutes': syncInterval.inMinutes,
        'healthCheckIntervalMinutes': healthCheckInterval.inMinutes,
        'verboseLogging': verboseLogging,
        'syncOnStartup': syncOnStartup,
      };

  factory AgentSettings.fromJson(Map<String, dynamic> json) {
    return AgentSettings(
      autoSync: json['autoSync'] as bool? ?? true,
      syncInterval: _clampMinutes(
        Duration(minutes: (json['syncIntervalMinutes'] as num?)?.toInt() ?? 15),
        _minSyncMinutes,
        _maxSyncMinutes,
      ),
      healthCheckInterval: _clampMinutes(
        Duration(
          minutes: (json['healthCheckIntervalMinutes'] as num?)?.toInt() ?? 2,
        ),
        _minHealthMinutes,
        _maxHealthMinutes,
      ),
      verboseLogging: json['verboseLogging'] as bool? ?? false,
      syncOnStartup: json['syncOnStartup'] as bool? ?? true,
    );
  }

  String encode() => jsonEncode(toJson());

  factory AgentSettings.decode(String raw) =>
      AgentSettings.fromJson(jsonDecode(raw) as Map<String, dynamic>);

  static Duration _clampMinutes(Duration d, int minM, int maxM) {
    final m = d.inMinutes.clamp(minM, maxM);
    return Duration(minutes: m);
  }
}
