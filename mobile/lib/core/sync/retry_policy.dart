import 'dart:math';

/// Exponential-backoff-with-jitter retry policy shared by the sync queue, the
/// delta processors and the store-agent network calls. Deterministic when
/// [jitter] is disabled, which keeps unit tests exact.
class RetryPolicy {
  const RetryPolicy({
    this.maxAttempts = 5,
    this.baseDelay = const Duration(seconds: 2),
    this.maxDelay = const Duration(minutes: 5),
    this.multiplier = 2.0,
    this.jitter = true,
  })  : assert(maxAttempts > 0),
        assert(multiplier >= 1.0);

  final int maxAttempts;
  final Duration baseDelay;
  final Duration maxDelay;
  final double multiplier;
  final bool jitter;

  /// A short, jitter-free policy suitable for tests.
  static const RetryPolicy test = RetryPolicy(
    maxAttempts: 3,
    baseDelay: Duration(milliseconds: 10),
    maxDelay: Duration(milliseconds: 100),
    jitter: false,
  );

  /// Whether an operation that has already been tried [attempt] times (1-based)
  /// should be tried again.
  bool shouldRetry(int attempt) => attempt < maxAttempts;

  /// Backoff before the [attempt]-th retry (1-based). Capped at [maxDelay];
  /// jittered by up to ±25% when [jitter] is set.
  Duration delayForAttempt(int attempt, {Random? random}) {
    final n = max(1, attempt);
    final rawMs = baseDelay.inMilliseconds * pow(multiplier, n - 1);
    final cappedMs = min(rawMs, maxDelay.inMilliseconds.toDouble());
    if (!jitter) return Duration(milliseconds: cappedMs.round());

    final rng = random ?? Random();
    // Full-range ±25% jitter.
    final delta = cappedMs * 0.25;
    final jittered = cappedMs - delta + rng.nextDouble() * (2 * delta);
    return Duration(milliseconds: jittered.round());
  }

  /// Absolute time the [attempt]-th retry becomes eligible.
  DateTime nextAttemptTime(int attempt, {DateTime? now, Random? random}) =>
      (now ?? DateTime.now()).add(delayForAttempt(attempt, random: random));

  /// Runs [action], retrying transient failures per this policy. [retryIf]
  /// decides whether a given error is worth retrying (default: everything).
  /// Rethrows the last error once attempts are exhausted.
  Future<T> execute<T>(
    Future<T> Function() action, {
    bool Function(Object error)? retryIf,
    Future<void> Function(Duration wait)? sleep,
  }) async {
    var attempt = 0;
    while (true) {
      try {
        return await action();
      } catch (e) {
        attempt++;
        if (!shouldRetry(attempt) || (retryIf != null && !retryIf(e))) {
          rethrow;
        }
        final wait = delayForAttempt(attempt);
        if (sleep != null) {
          await sleep(wait);
        } else {
          await Future<void>.delayed(wait);
        }
      }
    }
  }
}
