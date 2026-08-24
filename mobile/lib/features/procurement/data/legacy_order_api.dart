import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/procurement/domain/legacy_order_models.dart';

/// Typed access to the platform-admin Legacy Order endpoints.
class LegacyOrderApi {
  const LegacyOrderApi(this._dio);

  final Dio _dio;

  static const _base = '/api/legacy-order';

  Future<LegacyDbHealth> health() async => _getObject(
        '$_base/db/health',
        LegacyDbHealth.fromJson,
      );

  Future<List<LegacyStore>> stores() async => _getList(
        '$_base/stores',
        LegacyStore.fromJson,
        query: const {'active_only': true},
      );

  Future<LegacyDefaults> defaults() async => _getObject(
        '$_base/defaults',
        LegacyDefaults.fromJson,
      );

  Future<List<LegacyJob>> jobs({int limit = 20}) async => _getList(
        '$_base/jobs',
        LegacyJob.fromJson,
        query: {'limit': limit},
      );

  Future<LegacyJob> job(String id) async => _getObject(
        '$_base/jobs/$id',
        LegacyJob.fromJson,
      );

  Future<String> startSync(String storeName) => _start(
        '$_base/sync',
        {'store_name': storeName, 'tables': null},
      );

  Future<String> startOrderProcess({
    required String storeName,
    required int minDays,
    required int maxDays,
    required String mode,
  }) =>
      _start(
        '$_base/order-process',
        {
          'store_name': storeName,
          'min_days': minDays,
          'max_days': maxDays,
          'mode': mode,
        },
      );

  Future<String> startStockUpdate(
    String storeName, {
    String sourceStoreName = 'NMW',
  }) =>
      _start(
        '$_base/stock-update',
        {
          'store_name': storeName,
          'source_store_name': sourceStoreName,
        },
      );

  Future<List<PreviousOrder>> previousOrders(String storeName) => _getList(
        '$_base/previous-orders/${Uri.encodeComponent(storeName)}',
        PreviousOrder.fromJson,
      );

  Future<List<PreviousOrderSupplier>> previousOrderSuppliers({
    required String storeName,
    required int orderId,
  }) =>
      _getList(
        '$_base/previous-orders/${Uri.encodeComponent(storeName)}/$orderId/suppliers',
        PreviousOrderSupplier.fromJson,
      );

  Future<List<SupplierComparisonProduct>> previousOrderSupplierProducts({
    required String storeName,
    required int orderId,
    required String supplierCode,
  }) =>
      _getList(
        '$_base/previous-orders/${Uri.encodeComponent(storeName)}/$orderId/'
        'suppliers/${Uri.encodeComponent(supplierCode)}/products',
        SupplierComparisonProduct.fromJson,
      );

  Future<PreviousOrderComparison> comparePreviousOrder({
    required String storeName,
    required int orderId,
  }) =>
      _postObject(
        '$_base/compare-previous-order',
        {'store_name': storeName, 'order_id': orderId},
        PreviousOrderComparison.fromJson,
      );

  Future<PreviousOrderComparison> comparePreviousOrderSupplier({
    required String storeName,
    required int orderId,
    required String supplierCode,
  }) =>
      _postObject(
        '$_base/compare-previous-order/supplier',
        {
          'store_name': storeName,
          'order_id': orderId,
          'supplier_code': supplierCode,
        },
        PreviousOrderComparison.fromJson,
      );

  Future<List<QtyCheckRow>> qtyCheckRows(String storeName) => _getList(
        '$_base/qty-check/${Uri.encodeComponent(storeName)}',
        QtyCheckRow.fromJson,
      );

  Future<String> updateQtyCheck({
    required String storeName,
    required int productCode,
    required int orderQty,
  }) async {
    try {
      final response = await _dio.patch<Map<String, dynamic>>(
        '$_base/qty-check/${Uri.encodeComponent(storeName)}/$productCode',
        data: {'order_qty': orderQty},
      );
      return response.data?['remarks']?.toString() ?? 'Quantity reviewed.';
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<QtyCheckDetails> qtyCheckDetails({
    required String storeName,
    required int productCode,
    String mode = 'local',
  }) async {
    final store = Uri.encodeComponent(storeName);
    final root = '$_base/qty-check/$store/$productCode';
    final results = await Future.wait([
      _getList('$root/purchase-details', PurchaseDetail.fromJson,
          query: {'mode': mode}),
      _getList('$root/sales-details', SalesDetail.fromJson,
          query: {'mode': mode}),
      _getList('$root/monthly-stats', MonthlyStat.fromJson,
          query: {'mode': mode}),
      _getList('$root/order-history', OrderHistoryEntry.fromJson),
    ]);
    return QtyCheckDetails(
      purchases: results[0] as List<PurchaseDetail>,
      sales: results[1] as List<SalesDetail>,
      monthly: results[2] as List<MonthlyStat>,
      history: results[3] as List<OrderHistoryEntry>,
    );
  }

  Future<String> _start(String path, Map<String, dynamic> data) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(path, data: data);
      final id = response.data?['job_id']?.toString();
      if (id == null || id.isEmpty) {
        throw const ApiException(message: 'The server started no job.');
      }
      return id;
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<T> _getObject<T>(
    String path,
    T Function(Map<String, dynamic>) parse,
  ) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(path);
      return parse(response.data ?? const {});
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<T> _postObject<T>(
    String path,
    Map<String, dynamic> data,
    T Function(Map<String, dynamic>) parse,
  ) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(path, data: data);
      return parse(response.data ?? const {});
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<List<T>> _getList<T>(
    String path,
    T Function(Map<String, dynamic>) parse, {
    Map<String, dynamic>? query,
  }) async {
    try {
      final response = await _dio.get<List<dynamic>>(
        path,
        queryParameters: query,
      );
      return (response.data ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(parse)
          .toList(growable: false);
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }
}
