import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';

import 'package:nexora_mobile/core/services/app_logger.dart';

/// Coarse network status derived from the OS. This reports whether a network
/// interface is available — not whether the HO backend is reachable; that
/// (application-level) reachability lives in the store agent's health service.
enum NetworkStatus { online, offline }

extension NetworkStatusX on NetworkStatus {
  bool get isOnline => this == NetworkStatus.online;
  String get label => this == NetworkStatus.online ? 'Online' : 'Offline';
}

/// Wraps `connectivity_plus` behind a small, testable, broadcast surface.
///
/// The engine subscribes to [statusStream] to trigger automatic reconnect /
/// resume when the network returns, and to defer work when it drops.
class ConnectivityService {
  ConnectivityService([Connectivity? connectivity])
      : _connectivity = connectivity ?? Connectivity();

  final Connectivity _connectivity;
  final _log = AppLogger.of('Connectivity');

  final _controller = StreamController<NetworkStatus>.broadcast();
  StreamSubscription<List<ConnectivityResult>>? _sub;
  NetworkStatus _last = NetworkStatus.online;

  NetworkStatus get lastKnown => _last;

  /// Distinct network-status transitions. Starts emitting after [start].
  Stream<NetworkStatus> get statusStream => _controller.stream;

  /// Begins listening and seeds [lastKnown] with the current state.
  Future<void> start() async {
    _last = _map(await _connectivity.checkConnectivity());
    _sub ??= _connectivity.onConnectivityChanged.listen((results) {
      final next = _map(results);
      if (next != _last) {
        _last = next;
        _log.info('Network → ${next.label}');
        _controller.add(next);
      }
    });
  }

  /// One-shot probe of the current OS connectivity.
  Future<NetworkStatus> check() async =>
      _map(await _connectivity.checkConnectivity());

  Future<bool> get isOnline async => (await check()).isOnline;

  NetworkStatus _map(List<ConnectivityResult> results) {
    final offline =
        results.isEmpty || results.every((r) => r == ConnectivityResult.none);
    return offline ? NetworkStatus.offline : NetworkStatus.online;
  }

  Future<void> dispose() async {
    await _sub?.cancel();
    _sub = null;
    await _controller.close();
  }
}
