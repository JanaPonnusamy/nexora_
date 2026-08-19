import 'dart:async';
import 'dart:collection';

import 'package:flutter/foundation.dart';

import 'package:nexora_mobile/core/services/app_logger.dart';

/// One captured failure, kept so the app can show its own recent crashes.
class CrashRecord {
  const CrashRecord({
    required this.at,
    required this.summary,
    required this.detail,
    required this.fatal,
    this.context,
  });

  final DateTime at;

  /// First line — what a user or a support call can quote.
  final String summary;

  /// Error plus stack, for the diagnostics screen's expanded view.
  final String detail;

  /// True for errors that reached the framework's error handler, i.e. the ones
  /// that produced a red screen or killed a frame.
  final bool fatal;

  /// Where it happened, when the caller knows ('capture upload', 'sync').
  final String? context;
}

/// Where uncaught errors go.
///
/// An interface rather than a direct Crashlytics call because Firebase is not
/// provisioned yet (§1.3). Everything that reports an error already talks to
/// this, so adding Crashlytics later is a new implementation and one line in
/// bootstrap — not a hunt through the codebase for call sites.
abstract class CrashReporter {
  /// Record a failure. Must never throw: it is called from error handlers, and
  /// an error handler that fails takes the original error down with it.
  void recordError(
    Object error,
    StackTrace? stack, {
    bool fatal = false,
    String? context,
  });

  /// Breadcrumb. Cheap, and the thing that makes a stack trace legible later.
  void log(String message);

  /// Attach the signed-in user, so a report can be matched to a support call.
  /// Never pass anything that is not already on the device.
  void setUser({String? userId, String? storeId});
}

/// The default: logs, and keeps the last few failures in memory.
///
/// Without Crashlytics there is no server-side record, so the next best thing
/// is that the device can answer "what went wrong earlier?" itself — otherwise
/// a store user's only report is "it closed". The buffer is bounded and lives
/// only in RAM: crash detail can contain invoice values, and a crash log that
/// outlives the process is a data-retention question nobody has asked for.
class LoggingCrashReporter implements CrashReporter {
  LoggingCrashReporter({this.capacity = 20});

  final int capacity;
  final _log = AppLogger.of('Crash');
  final Queue<CrashRecord> _recent = Queue<CrashRecord>();

  String? _userId;
  String? _storeId;

  /// Most recent first.
  List<CrashRecord> get recent => _recent.toList().reversed.toList();

  @override
  void recordError(
    Object error,
    StackTrace? stack, {
    bool fatal = false,
    String? context,
  }) {
    final where = context == null ? '' : ' [$context]';
    _log.severe('${fatal ? 'FATAL' : 'Error'}$where: $error', error, stack);

    _recent.addLast(
      CrashRecord(
        at: DateTime.now(),
        summary: error.toString().split('\n').first,
        detail: '$error\n${stack ?? StackTrace.empty}',
        fatal: fatal,
        context: context,
      ),
    );
    while (_recent.length > capacity) {
      _recent.removeFirst();
    }
  }

  @override
  void log(String message) => _log.info(message);

  @override
  void setUser({String? userId, String? storeId}) {
    _userId = userId;
    _storeId = storeId;
    _log.info('Session context: user=$_userId store=$_storeId');
  }
}

/// Routes every uncaught error in the app into [reporter].
///
/// Three doors have to be covered, and missing any one of them means a class of
/// failure disappears silently in a release build:
///
///  * [FlutterError.onError] — errors thrown inside the framework (build,
///    layout, paint). This is the one that produces the red screen in debug and
///    nothing at all in release.
///  * [PlatformDispatcher.instance.onError] — uncaught *asynchronous* errors,
///    which is most of them in this app: every failed request, file write and
///    Drift query starts in a Future.
///  * [runZonedGuarded] around `runApp`, for anything raised before the
///    dispatcher hook is reachable.
void installCrashHandlers(CrashReporter reporter,
    {required void Function() run}) {
  final previousOnError = FlutterError.onError;

  FlutterError.onError = (details) {
    reporter.recordError(
      details.exception,
      details.stack,
      fatal: true,
      context: details.library,
    );
    // Chain rather than replace: the default handler is what prints the
    // formatted error to the console in debug, and losing that would make
    // local development strictly worse than before this existed.
    previousOnError?.call(details);
  };

  PlatformDispatcher.instance.onError = (error, stack) {
    reporter.recordError(error, stack, context: 'async');
    // true = handled. Returning false re-raises into the platform and, on
    // Android, ends the process — a failed background upload would take the
    // whole app down with it.
    return true;
  };

  runZonedGuarded(run, (error, stack) {
    reporter.recordError(error, stack, fatal: true, context: 'zone');
  });
}
