import 'package:flutter_test/flutter_test.dart';
import 'package:nexora_mobile/core/agent/agent_settings.dart';

void main() {
  group('AgentSettings', () {
    test('json round-trips', () {
      const settings = AgentSettings(
        autoSync: false,
        syncInterval: Duration(minutes: 30),
        healthCheckInterval: Duration(minutes: 5),
        verboseLogging: true,
        syncOnStartup: false,
      );
      final decoded = AgentSettings.decode(settings.encode());
      expect(decoded.autoSync, false);
      expect(decoded.syncInterval, const Duration(minutes: 30));
      expect(decoded.healthCheckInterval, const Duration(minutes: 5));
      expect(decoded.verboseLogging, true);
      expect(decoded.syncOnStartup, false);
    });

    test('clamps out-of-range intervals', () {
      final tooBig = AgentSettings.defaults.copyWith(
        syncInterval: const Duration(minutes: 9999),
        healthCheckInterval: const Duration(seconds: 1),
      );
      expect(tooBig.syncInterval, const Duration(minutes: 240));
      expect(tooBig.healthCheckInterval, const Duration(minutes: 1));
    });

    test('decode falls back on malformed values', () {
      final decoded = AgentSettings.fromJson({'syncIntervalMinutes': 0});
      // 0 is below the minimum and clamps to 1.
      expect(decoded.syncInterval, const Duration(minutes: 1));
      expect(decoded.autoSync, true); // default
    });
  });
}
