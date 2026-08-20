import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/features/procurement/data/legacy_order_api.dart';

class _LegacyAdapter implements HttpClientAdapter {
  final requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    final body = switch (options.path) {
      '/api/legacy-order/sync' => {'job_id': 'sync-1'},
      '/api/legacy-order/order-process' => {'job_id': 'order-1'},
      '/api/legacy-order/qty-check/Nathan%20Medicals/91' => {
          'order_qty': 7,
          'remarks': 'OrderQty Changed 5 Add',
        },
      _ when options.path.endsWith('/purchase-details') => [
          {'RStock': 10, 'SupplierName': 'NMW'}
        ],
      _ when options.path.endsWith('/sales-details') => [
          {'TotalQuantity': 2, 'CUSTOMERNAME': 'Cash'}
        ],
      _ when options.path.endsWith('/monthly-stats') => [
          {'MonthOfStatistics': '2026-08', 'SaleQuantity': 4}
        ],
      _ when options.path.endsWith('/order-history') => [
          {'Orqty': 3, 'remarks': 'Previous'}
        ],
      _ => <dynamic>[],
    };
    return ResponseBody.fromString(
      jsonEncode(body),
      200,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  late _LegacyAdapter adapter;
  late LegacyOrderApi api;

  setUp(() {
    adapter = _LegacyAdapter();
    final dio = Dio(BaseOptions(baseUrl: 'http://ho.test'))
      ..httpClientAdapter = adapter;
    api = LegacyOrderApi(dio);
  });

  test('sync sends the full-plan null explicitly', () async {
    expect(await api.startSync('Nathan Medicals'), 'sync-1');

    final request = adapter.requests.single;
    expect(request.path, '/api/legacy-order/sync');
    expect(request.data, {'store_name': 'Nathan Medicals', 'tables': null});
  });

  test('order process uses the router field names and selected mode', () async {
    expect(
      await api.startOrderProcess(
        storeName: 'Nathan Medicals',
        minDays: 13,
        maxDays: 18,
        mode: 'remote',
      ),
      'order-1',
    );

    expect(adapter.requests.single.data, {
      'store_name': 'Nathan Medicals',
      'min_days': 13,
      'max_days': 18,
      'mode': 'remote',
    });
  });

  test('qty update escapes the store and returns the audit remark', () async {
    final remark = await api.updateQtyCheck(
      storeName: 'Nathan Medicals',
      productCode: 91,
      orderQty: 7,
    );

    final request = adapter.requests.single;
    expect(request.path, '/api/legacy-order/qty-check/Nathan%20Medicals/91');
    expect(request.data, {'order_qty': 7});
    expect(remark, 'OrderQty Changed 5 Add');
  });

  test('evidence loads all four documented drill-downs', () async {
    final details = await api.qtyCheckDetails(
      storeName: 'Nathan Medicals',
      productCode: 91,
      mode: 'remote',
    );

    expect(adapter.requests, hasLength(4));
    expect(
      adapter.requests
          .take(3)
          .map((request) => request.queryParameters['mode']),
      everyElement('remote'),
    );
    expect(adapter.requests.last.queryParameters, isEmpty);
    expect(details.purchases.single.supplierName, 'NMW');
    expect(details.sales.single.quantity, 2);
    expect(details.monthly.single.month, '2026-08');
    expect(details.history.single.remarks, 'Previous');
  });
}
