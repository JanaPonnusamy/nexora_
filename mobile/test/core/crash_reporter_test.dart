import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/observability/crash_reporter.dart';

void main() {
  test('records the summary, the detail and whether it was fatal', () {
    final reporter = LoggingCrashReporter();

    reporter.recordError(
      StateError('supplier id missing\nsecond line'),
      StackTrace.current,
      fatal: true,
      context: 'capture upload',
    );

    final record = reporter.recent.single;
    expect(record.summary, contains('supplier id missing'));
    expect(record.summary, isNot(contains('second line')),
        reason: 'the summary is the quotable first line');
    expect(record.detail, contains('second line'));
    expect(record.fatal, isTrue);
    expect(record.context, 'capture upload');
  });

  test('most recent first — a diagnostics screen leads with what just broke',
      () {
    final reporter = LoggingCrashReporter();

    reporter.recordError(StateError('first'), null);
    reporter.recordError(StateError('second'), null);

    expect(reporter.recent.first.summary, contains('second'));
    expect(reporter.recent.last.summary, contains('first'));
  });

  test('the buffer is bounded — a crash loop must not exhaust memory', () {
    final reporter = LoggingCrashReporter(capacity: 3);

    for (var i = 0; i < 10; i++) {
      reporter.recordError(StateError('error $i'), null);
    }

    expect(reporter.recent, hasLength(3));
    expect(reporter.recent.first.summary, contains('error 9'));
    expect(reporter.recent.last.summary, contains('error 7'));
  });

  test('a null stack does not break capture', () {
    final reporter = LoggingCrashReporter();

    expect(
      () => reporter.recordError('plain string failure', null),
      returnsNormally,
    );
    expect(reporter.recent.single.summary, 'plain string failure');
  });
}
