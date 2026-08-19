import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/master_data/data/master_data_api_service.dart';
import 'package:nexora_mobile/features/master_data/domain/master_scope.dart';

/// Records the request Dio was about to make and answers it from a canned
/// payload — enough to assert *which* endpoint the sync calls, which is the
/// whole point of this change.
class RecordingAdapter implements HttpClientAdapter {
  RecordingAdapter({this.status = 200, Map<String, dynamic>? body})
      : body = body ?? const {'suppliers': []};

  final int status;
  final Map<String, dynamic> body;
  final requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    return ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  late RecordingAdapter adapter;
  late MasterDataApiService api;

  MasterDataApiService serviceWith(RecordingAdapter a) {
    final dio = Dio(BaseOptions(baseUrl: 'http://ho.test'))
      ..httpClientAdapter = a;
    return MasterDataApiService(dio);
  }

  setUp(() {
    adapter = RecordingAdapter(
      body: {
        'suppliers': [
          {'supplier_code': 'SUP-2041', 'supplier_name': 'Sri Balaji Pharma'},
          {'supplier_code': 'SUP-3102', 'supplier_name': 'Kumar Medical'},
        ],
      },
    );
    api = serviceWith(adapter);
  });

  const scope = MasterScope(tenantId: 't-1', storeId: 's-9');

  group('fetchSuppliers', () {
    test('calls the mobile BFF route, not the admin-gated one', () async {
      // The admin route 403s purchase-manager and salesman logins — the field
      // roles this app is for — leaving them with an empty supplier list.
      await api.fetchSuppliers(scope);

      expect(adapter.requests.single.path, '/api/mobile/v1/suppliers');
      expect(
        adapter.requests.single.path,
        isNot(contains('supplier-stock-analysis')),
      );
    });

    test('sends the store but never the tenant', () async {
      // Tenant is resolved from the token server-side, so a client cannot
      // widen its own scope by asking for another one.
      await api.fetchSuppliers(scope);

      final query = adapter.requests.single.queryParameters;
      expect(query['store_id'], 's-9');
      expect(query.containsKey('tenant_id'), isFalse);
    });

    test('reads the payload as a full snapshot', () async {
      final delta = await api.fetchSuppliers(scope);

      expect(delta, isNotNull);
      expect(delta!.records, hasLength(2));
      expect(delta.records.first['supplier_code'], 'SUP-2041');
      // Absent rows are reconciled as deletions by the repository, so this
      // flag is what keeps a removed supplier from lingering in the cache.
      expect(delta.fullSnapshot, isTrue);
      expect(delta.nextWatermark, isNotNull);
    });

    test('a malformed payload yields no records rather than throwing',
        () async {
      api = serviceWith(RecordingAdapter(body: {'suppliers': 'not-a-list'}));

      final delta = await api.fetchSuppliers(scope);

      expect(delta!.records, isEmpty);
    });

    test('no selected store means no call at all', () async {
      final delta = await api.fetchSuppliers(
        const MasterScope(tenantId: 't-1'),
      );

      expect(delta, isNull);
      expect(adapter.requests, isEmpty);
    });

    test('a refusal still surfaces as a typed error', () async {
      api = serviceWith(RecordingAdapter(status: 403, body: const {}));

      expect(
        () => api.fetchSuppliers(scope),
        throwsA(
          isA<ApiException>().having((e) => e.statusCode, 'statusCode', 403),
        ),
      );
    });
  });
}
