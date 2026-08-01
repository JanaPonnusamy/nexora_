import 'package:flutter_test/flutter_test.dart';
import 'package:nexora_mobile/core/sync/retry_policy.dart';

void main() {
  group('RetryPolicy', () {
    const policy = RetryPolicy(
      maxAttempts: 4,
      baseDelay: Duration(seconds: 1),
      maxDelay: Duration(seconds: 30),
      multiplier: 2,
      jitter: false,
    );

    test('shouldRetry respects maxAttempts', () {
      expect(policy.shouldRetry(1), isTrue);
      expect(policy.shouldRetry(3), isTrue);
      expect(policy.shouldRetry(4), isFalse);
      expect(policy.shouldRetry(5), isFalse);
    });

    test('delay grows exponentially and caps at maxDelay', () {
      expect(policy.delayForAttempt(1), const Duration(seconds: 1));
      expect(policy.delayForAttempt(2), const Duration(seconds: 2));
      expect(policy.delayForAttempt(3), const Duration(seconds: 4));
      expect(policy.delayForAttempt(4), const Duration(seconds: 8));
      // 2^9 = 512s would exceed the 30s cap.
      expect(policy.delayForAttempt(10), const Duration(seconds: 30));
    });

    test('execute retries then succeeds', () async {
      var calls = 0;
      final result = await RetryPolicy.test.execute<int>(
        () async {
          calls++;
          if (calls < 3) throw StateError('boom');
          return 42;
        },
      );
      expect(result, 42);
      expect(calls, 3);
    });

    test('execute rethrows after exhausting attempts', () async {
      var calls = 0;
      await expectLater(
        RetryPolicy.test.execute<int>(() async {
          calls++;
          throw StateError('always');
        }),
        throwsStateError,
      );
      expect(calls, RetryPolicy.test.maxAttempts);
    });

    test('execute stops early when retryIf returns false', () async {
      var calls = 0;
      await expectLater(
        RetryPolicy.test.execute<int>(
          () async {
            calls++;
            throw ArgumentError('fatal');
          },
          retryIf: (e) => e is! ArgumentError,
        ),
        throwsArgumentError,
      );
      expect(calls, 1);
    });
  });
}
