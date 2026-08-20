import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/sync/sync_repository.dart';

/// Severity levels persisted to `sync_history`.
enum SyncLogLevel { fine, info, warning, error }

/// Durable, queryable sync log. Writes go to both the Dart DevTools console
/// (via [AppLogger]) and the `sync_history` table so the Sync Status screen can
/// render an activity feed and diagnostics survive a restart.
///
/// History is trimmed opportunistically to stay bounded.
class SyncLogger {
  SyncLogger(this._repo, {this.maxRows = 500});

  final SyncRepository _repo;
  final int maxRows;
  final _log = AppLogger.of('Sync');

  int _writesSinceTrim = 0;

  Future<void> log(
    SyncLogLevel level,
    String message, {
    String category = 'sync',
    String? entity,
    String? detail,
  }) async {
    switch (level) {
      case SyncLogLevel.fine:
        _log.fine(message);
      case SyncLogLevel.info:
        _log.info(message);
      case SyncLogLevel.warning:
        _log.warning(message);
      case SyncLogLevel.error:
        _log.severe(message);
    }

    await _repo.appendHistory(
      level: level.name,
      category: category,
      message: message,
      entity: entity,
      detail: detail,
    );

    // Trim every ~50 writes rather than on every call.
    if (++_writesSinceTrim >= 50) {
      _writesSinceTrim = 0;
      await _repo.trimHistory(keep: maxRows);
    }
  }

  Future<void> fine(String m, {String category = 'sync', String? entity}) =>
      log(SyncLogLevel.fine, m, category: category, entity: entity);

  Future<void> info(String m, {String category = 'sync', String? entity}) =>
      log(SyncLogLevel.info, m, category: category, entity: entity);

  Future<void> warning(
    String m, {
    String category = 'sync',
    String? entity,
    String? detail,
  }) =>
      log(
        SyncLogLevel.warning,
        m,
        category: category,
        entity: entity,
        detail: detail,
      );

  Future<void> error(
    String m, {
    String category = 'sync',
    String? entity,
    String? detail,
  }) =>
      log(
        SyncLogLevel.error,
        m,
        category: category,
        entity: entity,
        detail: detail,
      );
}
