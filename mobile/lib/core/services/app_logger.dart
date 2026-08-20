import 'dart:developer' as developer;

import 'package:logging/logging.dart';

/// Thin wrapper over the `logging` package that gives every subsystem a named
/// logger and routes records to the Dart DevTools console.
///
/// Call [AppLogger.init] once during bootstrap. Verbose (FINE) output is
/// suppressed in production builds — see wiring in `bootstrap`.
class AppLogger {
  AppLogger._();

  static bool _initialised = false;

  static void init({required bool verbose}) {
    if (_initialised) return;
    _initialised = true;

    Logger.root.level = verbose ? Level.ALL : Level.INFO;
    Logger.root.onRecord.listen((record) {
      developer.log(
        record.message,
        time: record.time,
        level: record.level.value,
        name: record.loggerName,
        error: record.error,
        stackTrace: record.stackTrace,
      );
    });
  }

  /// Returns a named logger, e.g. `AppLogger.of('DioClient')`.
  static Logger of(String name) => Logger(name);
}
