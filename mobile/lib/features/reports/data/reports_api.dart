import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/reports/domain/report_models.dart';

/// Typed client for `/api/reports/*`.
///
/// Paths and parameter names were read off `backend/modules/reports/router.py`.
/// Note the date parameters are `from`/`to` on the wire (aliased from
/// `from_date`/`to_date` in the handler) — sending `from_date` silently gets an
/// unfiltered report rather than an error.
class ReportsApi {
  const ReportsApi(this._dio);

  final Dio _dio;

  static const String _base = '/api/reports';

  /// The catalog. Not tenant-scoped and needs no inputs — it is pure metadata.
  Future<List<ReportDef>> catalog() async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(_base);
      final reports = res.data?['reports'];
      if (reports is! List) return const [];
      return reports
          .whereType<Map<String, dynamic>>()
          .map(ReportDef.fromJson)
          .toList(growable: false);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Runs one report. Only the filters the report declares are sent; the
  /// server ignores unknown combinations but sending a date range to a stock
  /// report just makes the query slower for no reason.
  Future<ReportResult> run({
    required ReportDef def,
    required String tenantId,
    required String storeId,
    required ReportFilters filters,
  }) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        '$_base/${def.key}',
        queryParameters: {
          'tenant_id': tenantId,
          'store_id': storeId,
          if (def.needsDateRange && filters.from != null)
            'from': _date(filters.from!),
          if (def.needsDateRange && filters.to != null)
            'to': _date(filters.to!),
          if (def.needsDwellDays && filters.dwellDays != null)
            'dwell_days': filters.dwellDays,
          if (def.needsSupplier && filters.supplierCode != null)
            'supplier_code': filters.supplierCode,
          if (def.needsDivision && filters.divisionCode != null)
            'division_code': filters.divisionCode,
        },
      );
      return ReportResult.fromJson(res.data ?? const {});
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Supplier lookup for the Non-Moving / Purchased-Not-Sold filters.
  Future<List<SupplierOption>> suppliers({
    required String tenantId,
    required String storeId,
    String query = '',
    int limit = 30,
  }) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        '$_base/suppliers',
        queryParameters: {
          'tenant_id': tenantId,
          'store_id': storeId,
          'q': query,
          'limit': limit,
        },
      );
      final suppliers = res.data?['suppliers'];
      if (suppliers is! List) return const [];
      return suppliers
          .whereType<Map<String, dynamic>>()
          .map(SupplierOption.fromJson)
          .where((s) => s.code.isNotEmpty)
          .toList(growable: false);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// `YYYY-MM-DD`, the only format the report SQL parses.
  static String _date(DateTime d) => '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';
}
