String? _text(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? null : text;
}

int _integer(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

double _number(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '') ?? 0;
}

bool _boolean(Object? value) => value == true || value == 1 || value == '1';

class DistributionTarget {
  const DistributionTarget({
    required this.storeId,
    required this.storeCode,
    required this.storeName,
    required this.enabled,
    this.localSupplierCode,
    this.whatsappGroup,
    this.phoneNumber,
  });

  final String storeId;
  final String storeCode;
  final String storeName;
  final bool enabled;
  final String? localSupplierCode;
  final String? whatsappGroup;
  final String? phoneNumber;

  bool get ready => enabled && localSupplierCode != null;

  factory DistributionTarget.fromJson(Map<String, dynamic> json) =>
      DistributionTarget(
        storeId: _text(json['store_id']) ?? '',
        storeCode: _text(json['store_code']) ?? '',
        storeName: _text(json['store_name']) ?? 'Unnamed store',
        enabled: _boolean(json['enabled']),
        localSupplierCode: _text(json['local_supplier_code']),
        whatsappGroup: _text(json['whatsapp_group']),
        phoneNumber: _text(json['phone_number']),
      );
}

class DistributionRun {
  const DistributionRun({
    required this.runId,
    required this.sourceStoreCode,
    required this.status,
    required this.storesTotal,
    required this.storesSucceeded,
    required this.storesFailed,
    required this.totalProducts,
    required this.totalStockQty,
    this.startedAt,
    this.finishedAt,
    this.error,
  });

  final String runId;
  final String sourceStoreCode;
  final String status;
  final int storesTotal;
  final int storesSucceeded;
  final int storesFailed;
  final int totalProducts;
  final double totalStockQty;
  final DateTime? startedAt;
  final DateTime? finishedAt;
  final String? error;

  factory DistributionRun.fromJson(Map<String, dynamic> json) =>
      DistributionRun(
        runId: _text(json['run_id']) ?? '',
        sourceStoreCode: _text(json['source_store_code']) ?? '',
        status: (_text(json['status']) ?? 'unknown').toLowerCase(),
        storesTotal: _integer(json['stores_total']),
        storesSucceeded: _integer(json['stores_succeeded']),
        storesFailed: _integer(json['stores_failed']),
        totalProducts: _integer(json['total_products']),
        totalStockQty: _number(json['total_stock_qty']),
        startedAt: DateTime.tryParse(_text(json['started_at']) ?? ''),
        finishedAt: DateTime.tryParse(_text(json['finished_at']) ?? ''),
        error: _text(json['error_summary'] ?? json['error']),
      );
}

class DistributionRunItem {
  const DistributionRunItem({
    required this.runItemId,
    required this.storeCode,
    required this.status,
    required this.stockStatus,
    required this.excelStatus,
    required this.whatsappStatus,
    required this.rowsExported,
    this.error,
  });

  final String runItemId;
  final String storeCode;
  final String status;
  final String stockStatus;
  final String excelStatus;
  final String whatsappStatus;
  final int rowsExported;
  final String? error;

  factory DistributionRunItem.fromJson(Map<String, dynamic> json) =>
      DistributionRunItem(
        runItemId: _text(json['run_item_id']) ?? '',
        storeCode: _text(json['store_code']) ?? '',
        status: (_text(json['status']) ?? 'unknown').toLowerCase(),
        stockStatus: (_text(json['stock_status']) ?? 'skipped').toLowerCase(),
        excelStatus: (_text(json['excel_status']) ?? 'skipped').toLowerCase(),
        whatsappStatus:
            (_text(json['whatsapp_status']) ?? 'not_queued').toLowerCase(),
        rowsExported: _integer(json['rows_exported'] ?? json['rows']),
        error: _text(json['error_message'] ??
            json['stock_error'] ??
            json['excel_error'] ??
            json['error']),
      );
}

class DistributionRunDetail {
  const DistributionRunDetail({required this.run, required this.items});

  final DistributionRun? run;
  final List<DistributionRunItem> items;

  factory DistributionRunDetail.fromJson(Map<String, dynamic> json) {
    final run = json['run'];
    return DistributionRunDetail(
      run: run is Map
          ? DistributionRun.fromJson(run.cast<String, dynamic>())
          : null,
      items: (json['items'] as List? ?? const [])
          .whereType<Map>()
          .map((row) =>
              DistributionRunItem.fromJson(row.cast<String, dynamic>()))
          .toList(growable: false),
    );
  }
}

class DistributionResult {
  const DistributionResult({
    required this.runId,
    required this.succeeded,
    required this.failed,
    this.error,
  });

  final String? runId;
  final int succeeded;
  final int failed;
  final String? error;

  factory DistributionResult.fromJson(Map<String, dynamic> json) =>
      DistributionResult(
        runId: _text(json['run_id']),
        succeeded: _integer(json['stores_succeeded']),
        failed: _integer(json['stores_failed']),
        error: _text(json['error']),
      );
}
