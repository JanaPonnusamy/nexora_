import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/sync/connectivity_service.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/core/widgets/offline_banner.dart';

/// Connectivity double. The real service reaches a platform channel that does
/// not exist under `flutter test`.
class _FakeConnectivity extends ConnectivityService {
  _FakeConnectivity(this._current) : super(Connectivity());

  NetworkStatus _current;
  final _controller = StreamController<NetworkStatus>.broadcast();

  @override
  Stream<NetworkStatus> get statusStream => _controller.stream;

  @override
  NetworkStatus get lastKnown => _current;

  @override
  Future<NetworkStatus> check() async => _current;

  void emit(NetworkStatus status) {
    _current = status;
    _controller.add(status);
  }

  @override
  Future<void> dispose() async => _controller.close();
}

Future<void> _pumpBanner(WidgetTester tester, _FakeConnectivity conn) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [connectivityServiceProvider.overrideWithValue(conn)],
      child: MaterialApp(
        theme: AppTheme.dark,
        home: const Scaffold(body: OfflineBanner()),
      ),
    ),
  );
  // One pump to mount, one to let the initial probe resolve.
  await tester.pump();
  await tester.pump();
}

void main() {
  testWidgets('shows nothing while online', (tester) async {
    final conn = _FakeConnectivity(NetworkStatus.online);
    addTearDown(conn.dispose);

    await _pumpBanner(tester, conn);

    expect(find.textContaining('Offline'), findsNothing);
  });

  testWidgets(
      'appears on a cold start that is already offline — the service stream '
      'only carries transitions, so a seed probe is what makes this work',
      (tester) async {
    final conn = _FakeConnectivity(NetworkStatus.offline);
    addTearDown(conn.dispose);

    await _pumpBanner(tester, conn);

    expect(find.textContaining('Offline'), findsOneWidget);
  });

  testWidgets('says what still works, not just what is wrong', (tester) async {
    final conn = _FakeConnectivity(NetworkStatus.offline);
    addTearDown(conn.dispose);

    await _pumpBanner(tester, conn);

    expect(find.textContaining('will sync later'), findsOneWidget);
  });

  testWidgets('follows the network down and back up', (tester) async {
    final conn = _FakeConnectivity(NetworkStatus.online);
    addTearDown(conn.dispose);

    await _pumpBanner(tester, conn);
    expect(find.textContaining('Offline'), findsNothing);

    conn.emit(NetworkStatus.offline);
    await tester.pumpAndSettle();
    expect(find.textContaining('Offline'), findsOneWidget);

    conn.emit(NetworkStatus.online);
    await tester.pumpAndSettle();
    expect(find.textContaining('Offline'), findsNothing);
  });

  testWidgets('a screen can override the message', (tester) async {
    final conn = _FakeConnectivity(NetworkStatus.offline);
    addTearDown(conn.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [connectivityServiceProvider.overrideWithValue(conn)],
        child: MaterialApp(
          theme: AppTheme.dark,
          home: const Scaffold(
            body: OfflineBanner(message: 'Live sync needs a connection.'),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.text('Live sync needs a connection.'), findsOneWidget);
  });
}
