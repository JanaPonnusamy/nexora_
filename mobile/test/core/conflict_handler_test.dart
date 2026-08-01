import 'package:flutter_test/flutter_test.dart';
import 'package:nexora_mobile/core/sync/conflict_handler.dart';

void main() {
  group('ConflictHandler', () {
    final t0 = DateTime(2026, 1, 1, 10);
    final t1 = DateTime(2026, 1, 1, 11);

    test('no conflict when versions match', () {
      const handler = ConflictHandler();
      expect(
        handler.hasConflict(
          const Revision(version: 3),
          const Revision(version: 3),
        ),
        isFalse,
      );
      expect(
        handler.resolve(
          const Revision(version: 3),
          const Revision(version: 3),
        ),
        ConflictResolution.noChange,
      );
    });

    test('empty local + non-empty server is a conflict (new record)', () {
      const handler = ConflictHandler();
      expect(
        handler.hasConflict(const Revision(), const Revision(version: 1)),
        isTrue,
      );
    });

    test('serverWins always takes server on conflict', () {
      const handler = ConflictHandler(strategy: ConflictStrategy.serverWins);
      expect(
        handler.resolve(
          const Revision(version: 1),
          const Revision(version: 2),
        ),
        ConflictResolution.takeServer,
      );
    });

    test('clientWins always takes client on conflict', () {
      const handler = ConflictHandler(strategy: ConflictStrategy.clientWins);
      expect(
        handler.resolve(
          const Revision(version: 1),
          const Revision(version: 2),
        ),
        ConflictResolution.takeClient,
      );
    });

    test('lastWriteWins by version', () {
      const handler = ConflictHandler(strategy: ConflictStrategy.lastWriteWins);
      expect(
        handler.resolve(
          const Revision(version: 5),
          const Revision(version: 2),
        ),
        ConflictResolution.takeClient,
      );
      expect(
        handler.resolve(
          const Revision(version: 2),
          const Revision(version: 5),
        ),
        ConflictResolution.takeServer,
      );
    });

    test('lastWriteWins by timestamp when no versions', () {
      const handler = ConflictHandler(strategy: ConflictStrategy.lastWriteWins);
      expect(
        handler.resolve(
          Revision(updatedAt: t0),
          Revision(updatedAt: t1),
        ),
        ConflictResolution.takeServer,
      );
      expect(
        handler.resolve(
          Revision(updatedAt: t1),
          Revision(updatedAt: t0),
        ),
        ConflictResolution.takeClient,
      );
    });
  });
}
