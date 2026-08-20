import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexora_mobile/core/api/api_endpoints.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/sync/data/sync_admin_service.dart';

/// Minimal fake transport so the service is tested end-to-end (request path,
/// JSON decode, error mapping) without touching a real network.
class _FakeAdapter implements HttpClientAdapter {
  _FakeAdapter(this.statusCode, this.body);
  final int statusCode;
  final Map<String, dynamic> body;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final bytes = utf8.encode(jsonEncode(body));
    return ResponseBody.fromBytes(
      bytes,
      statusCode,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

Dio _dioWith(int statusCode, Map<String, dynamic> body) {
  final dio = Dio(BaseOptions(baseUrl: 'http://backend.test'));
  dio.httpClientAdapter = _FakeAdapter(statusCode, body);
  return dio;
}

void main() {
  test('fetchControlCenter hits the documented endpoint and parses the body',
      () async {
    final dio = _dioWith(200, {
      'kpis': {
        'stores_online': 6,
        'stores_offline': 0,
        'sync_running': 0,
        'queued': 0,
        'completed_today': 6,
        'failed_today': 0,
      },
      'stores': [
        {
          'store_id': 's1',
          'store_code': 'NMA',
          'store_name': 'Nathan Medicals A',
          'agent_status': 'Online',
          'current_activity': 'Idle',
          'is_syncing': false,
          'status': 'Online',
        },
      ],
    });
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          expect(options.path, ApiEndpoints.syncControlCenter);
          handler.next(options);
        },
      ),
    );

    final result = await SyncAdminService(dio).fetchControlCenter();

    expect(result.kpis.storesOnline, 6);
    expect(result.stores.single.storeCode, 'NMA');
  });

  test('a server error is surfaced as an ApiException', () async {
    final dio = _dioWith(500, {'detail': 'boom'});
    await expectLater(
      SyncAdminService(dio).fetchControlCenter(),
      throwsA(isA<ApiException>()),
    );
  });
}
