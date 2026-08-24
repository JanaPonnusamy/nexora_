library;

/// Mobile-facing models for the old OrderNMC console.
///
/// The legacy database returns its original SQL column casing, while the
/// operational endpoints use snake_case. Parsing stays defensive because SQL
/// drivers can also return decimals and dates as strings.
class LegacyStore {
  const LegacyStore({
    required this.code,
    required this.name,
    required this.server,
    required this.database,
    required this.isActive,
    this.lastSyncAt,
    this.lastSyncStatus,
  });

  final String code;
  final String name;
  final String server;
  final String database;
  final bool isActive;
  final DateTime? lastSyncAt;
  final String? lastSyncStatus;

  bool get lastSyncFailed => lastSyncStatus?.toLowerCase() == 'failed';
  bool get lastSyncSucceeded => lastSyncStatus?.toLowerCase() == 'success';

  factory LegacyStore.fromJson(Map<String, dynamic> json) => LegacyStore(
        code: _text(json['store_code']) ?? '',
        name: _text(json['store_name']) ?? 'Unnamed store',
        server: _text(json['server_name']) ?? '',
        database: _text(json['database']) ?? '',
        isActive: _bool(json['is_active'], fallback: true),
        lastSyncAt: _date(json['last_sync_time']),
        lastSyncStatus: _text(json['last_sync_status']),
      );
}

class LegacyDbHealth {
  const LegacyDbHealth({
    required this.database,
    required this.server,
    required this.reachable,
    required this.online,
    required this.message,
    this.state,
    this.access,
  });

  final String database;
  final String server;
  final bool reachable;
  final bool online;
  final String? state;
  final String? access;
  final String message;

  factory LegacyDbHealth.fromJson(Map<String, dynamic> json) => LegacyDbHealth(
        database: _text(json['database']) ?? 'OrderNMC',
        server: _text(json['server']) ?? '',
        reachable: _bool(json['reachable']),
        online: _bool(json['online']),
        state: _text(json['state']),
        access: _text(json['access']),
        message: _text(json['message']) ?? 'No database status was returned.',
      );
}

class LegacyDefaults {
  const LegacyDefaults({required this.minDays, required this.maxDays});

  final int minDays;
  final int maxDays;

  factory LegacyDefaults.fromJson(Map<String, dynamic> json) => LegacyDefaults(
        minDays: _integer(json['min_days']) ?? 13,
        maxDays: _integer(json['max_days']) ?? 18,
      );
}

enum LegacyJobKind {
  sync,
  order,
  stock,
  unknown;

  static LegacyJobKind fromWire(Object? value) => switch (_text(value)) {
        'sync' => LegacyJobKind.sync,
        'order' => LegacyJobKind.order,
        'stock' => LegacyJobKind.stock,
        _ => LegacyJobKind.unknown,
      };

  String get label => switch (this) {
        LegacyJobKind.sync => 'Sync',
        LegacyJobKind.order => 'Order process',
        LegacyJobKind.stock => 'Stock update',
        LegacyJobKind.unknown => 'Legacy job',
      };
}

enum LegacyJobStatus {
  running,
  completed,
  failed,
  unknown;

  static LegacyJobStatus fromWire(Object? value) => switch (_text(value)) {
        'running' => LegacyJobStatus.running,
        'completed' => LegacyJobStatus.completed,
        'failed' => LegacyJobStatus.failed,
        _ => LegacyJobStatus.unknown,
      };
}

class LegacyJobLogEntry {
  const LegacyJobLogEntry({required this.message, this.at});

  final String message;
  final DateTime? at;

  factory LegacyJobLogEntry.fromJson(Map<String, dynamic> json) =>
      LegacyJobLogEntry(
        message: _text(json['message']) ?? '',
        at: _date(json['at']),
      );
}

class LegacyJob {
  const LegacyJob({
    required this.id,
    required this.kind,
    required this.rawKind,
    required this.storeName,
    required this.status,
    required this.rawStatus,
    required this.step,
    required this.totalSteps,
    required this.message,
    required this.log,
    this.error,
    this.startedAt,
    this.finishedAt,
  });

  final String id;
  final LegacyJobKind kind;
  final String rawKind;
  final String storeName;
  final LegacyJobStatus status;
  final String rawStatus;
  final int step;
  final int totalSteps;
  final String message;
  final List<LegacyJobLogEntry> log;
  final String? error;
  final DateTime? startedAt;
  final DateTime? finishedAt;

  bool get isRunning => status == LegacyJobStatus.running;
  double get progress => totalSteps <= 0 ? 0 : (step / totalSteps).clamp(0, 1);

  String get statusLabel => switch (status) {
        LegacyJobStatus.running => 'Running',
        LegacyJobStatus.completed => 'Complete',
        LegacyJobStatus.failed => 'Failed',
        LegacyJobStatus.unknown => rawStatus.isEmpty ? 'Unknown' : rawStatus,
      };

  factory LegacyJob.fromJson(Map<String, dynamic> json) {
    final kind = _text(json['kind']) ?? '';
    final status = _text(json['status']) ?? '';
    return LegacyJob(
      id: _text(json['job_id']) ?? '',
      kind: LegacyJobKind.fromWire(kind),
      rawKind: kind,
      storeName: _text(json['store_name']) ?? '',
      status: LegacyJobStatus.fromWire(status),
      rawStatus: status,
      step: _integer(json['step']) ?? 0,
      totalSteps: _integer(json['total_steps']) ?? 0,
      message: _text(json['message']) ?? '',
      log: _maps(json['log'])
          .map(LegacyJobLogEntry.fromJson)
          .toList(growable: false),
      error: _text(json['error']),
      startedAt: _date(json['started_at']),
      finishedAt: _date(json['finished_at']),
    );
  }
}

class LegacyConsoleData {
  const LegacyConsoleData({
    required this.stores,
    required this.jobs,
    required this.defaults,
  });

  final List<LegacyStore> stores;
  final List<LegacyJob> jobs;
  final LegacyDefaults defaults;

  bool get hasRunningJobs => jobs.any((job) => job.isRunning);
}

class PreviousOrder {
  const PreviousOrder({
    required this.storeName,
    required this.orderId,
    required this.wantedAt,
  });

  final String storeName;
  final int orderId;
  final DateTime? wantedAt;

  factory PreviousOrder.fromJson(Map<String, dynamic> json) => PreviousOrder(
        storeName: _text(json['store_name']) ?? '',
        orderId: _integer(json['order_id']) ?? 0,
        wantedAt: _date(json['wanted_date']),
      );
}

class PreviousOrderComparison {
  const PreviousOrderComparison({
    required this.storeName,
    required this.orderId,
    required this.affectedRows,
    this.supplierCode,
  });

  final String storeName;
  final int orderId;
  final int affectedRows;
  final String? supplierCode;

  factory PreviousOrderComparison.fromJson(Map<String, dynamic> json) =>
      PreviousOrderComparison(
        storeName: _text(json['store_name']) ?? '',
        orderId: _integer(json['order_id']) ?? 0,
        affectedRows: _integer(json['affected_rows']) ?? 0,
        supplierCode: _text(json['supplier_code']),
      );
}

class PreviousOrderSupplier {
  const PreviousOrderSupplier({
    required this.code,
    required this.name,
    required this.productCount,
  });

  final String code;
  final String name;
  final int productCount;

  factory PreviousOrderSupplier.fromJson(Map<String, dynamic> json) =>
      PreviousOrderSupplier(
        code: _text(json['supplier_code']) ?? '',
        name: _text(json['supplier_name']) ?? 'Unnamed supplier',
        productCount: _integer(json['product_count']) ?? 0,
      );
}

class SupplierComparisonProduct {
  const SupplierComparisonProduct({
    required this.previousProductCode,
    required this.previousProductName,
    this.currentProductCode,
    this.currentProductName,
    this.currentOrderQty,
    this.currentWantedType,
    this.previousOrderedQty,
    this.previousStock,
    this.currentStock,
    this.previousRemarks,
    this.previousStatus,
  });

  final int? currentProductCode;
  final String? currentProductName;
  final num? currentOrderQty;
  final String? currentWantedType;
  final int previousProductCode;
  final String previousProductName;
  final num? previousOrderedQty;
  final num? previousStock;
  final num? currentStock;
  final String? previousRemarks;
  final int? previousStatus;

  String get productName => currentProductName ?? previousProductName;
  bool get changed =>
      previousOrderedQty != currentOrderQty || previousStock != currentStock;

  factory SupplierComparisonProduct.fromJson(Map<String, dynamic> json) =>
      SupplierComparisonProduct(
        currentProductCode: _integer(json['CurrentProductCode']),
        currentProductName: _text(json['CurrentProductName']),
        currentOrderQty: _number(json['CurrentOrderQty']),
        currentWantedType: _text(json['CurrentWantedType']),
        previousProductCode: _integer(json['PreviousProductCode']) ?? 0,
        previousProductName:
            _text(json['PreviousProductName']) ?? 'Unnamed product',
        previousOrderedQty: _number(json['PreviousOrderedQty']),
        previousStock: _number(json['PreviousStock']),
        currentStock: _number(json['CurrentStock']),
        previousRemarks: _text(json['PreviousRemarks']),
        previousStatus: _integer(json['PreviousStatus']),
      );
}

class QtyCheckRow {
  const QtyCheckRow({
    required this.productCode,
    required this.productName,
    required this.orderQty,
    required this.totalStock,
    required this.saleUnit,
    required this.salesQty,
    required this.mrp,
    required this.maxSaleQty,
    this.unitDescription,
    this.lastReceivedAt,
    this.lastSoldAt,
    this.transactionAt,
    this.wantedType,
  });

  final int productCode;
  final String productName;
  final int orderQty;
  final num totalStock;
  final num saleUnit;
  final num salesQty;
  final num mrp;
  final num maxSaleQty;
  final String? unitDescription;
  final DateTime? lastReceivedAt;
  final DateTime? lastSoldAt;
  final DateTime? transactionAt;
  final String? wantedType;

  factory QtyCheckRow.fromJson(Map<String, dynamic> json) => QtyCheckRow(
        productCode: _integer(json['productcode']) ?? 0,
        productName: _text(json['productname']) ?? 'Unnamed product',
        orderQty: _integer(json['orderqty']) ?? 0,
        totalStock: _number(json['totalstock']) ?? 0,
        saleUnit: _number(json['saleunit']) ?? 0,
        salesQty: _number(json['slsqty']) ?? 0,
        mrp: _number(json['mrp']) ?? 0,
        maxSaleQty: _number(json['maxsaleqty']) ?? 0,
        unitDescription: _text(json['unitdescription']),
        lastReceivedAt: _date(json['lastreceiveddate']),
        lastSoldAt: _date(json['lastsaledate']),
        transactionAt: _date(json['Transactiondate']),
        wantedType: _text(json['wantedtype']),
      );
}

class PurchaseDetail {
  const PurchaseDetail({
    this.receivedStock,
    this.freeQty,
    this.discount,
    this.itemCost,
    this.ptr,
    this.mrp,
    this.grnAt,
    this.supplierName,
  });

  final num? receivedStock;
  final num? freeQty;
  final num? discount;
  final num? itemCost;
  final num? ptr;
  final num? mrp;
  final DateTime? grnAt;
  final String? supplierName;

  factory PurchaseDetail.fromJson(Map<String, dynamic> json) => PurchaseDetail(
        receivedStock: _number(json['RStock']),
        freeQty: _number(json['FreeQty']),
        discount: _number(json['DIS']),
        itemCost: _number(json['ItemCost']),
        ptr: _number(json['PTR']),
        mrp: _number(json['MRP']),
        grnAt: _date(json['GRNDate']),
        supplierName: _text(json['SupplierName']),
      );
}

class SalesDetail {
  const SalesDetail({
    this.quantity,
    this.billAt,
    this.salesperson,
    this.customer,
    this.discount,
    this.type,
    this.mrp,
    this.billNumber,
  });

  final num? quantity;
  final DateTime? billAt;
  final String? salesperson;
  final String? customer;
  final num? discount;
  final String? type;
  final num? mrp;
  final String? billNumber;

  factory SalesDetail.fromJson(Map<String, dynamic> json) => SalesDetail(
        quantity: _number(json['TotalQuantity']),
        billAt: _date(json['Bill_Time']),
        salesperson: _text(json['Salesmanname']),
        customer: _text(json['CUSTOMERNAME']),
        discount: _number(json['dis']),
        type: _text(json['type']),
        mrp: _number(json['mrp']),
        billNumber: _text(json['Bnumber']),
      );
}

class MonthlyStat {
  const MonthlyStat({
    required this.month,
    required this.sales,
    required this.stock,
    required this.purchases,
  });

  final String month;
  final num sales;
  final num stock;
  final num purchases;

  factory MonthlyStat.fromJson(Map<String, dynamic> json) => MonthlyStat(
        month: _text(json['MonthOfStatistics']) ?? '—',
        sales: _number(json['SaleQuantity']) ?? 0,
        stock: _number(json['StockInHand']) ?? 0,
        purchases: _number(json['PurchaseQuantity']) ?? 0,
      );
}

class OrderHistoryEntry {
  const OrderHistoryEntry({
    this.orderQty,
    this.originalOrderQty,
    this.remarks,
    this.wantedAt,
    this.wantedType,
    this.supplier,
  });

  final num? orderQty;
  final num? originalOrderQty;
  final String? remarks;
  final DateTime? wantedAt;
  final String? wantedType;
  final String? supplier;

  factory OrderHistoryEntry.fromJson(Map<String, dynamic> json) =>
      OrderHistoryEntry(
        orderQty: _number(json['Orqty']),
        originalOrderQty: _number(json['OrgOrderQty']),
        remarks: _text(json['remarks']),
        wantedAt: _date(json['Wanteddate']),
        wantedType: _text(json['WantedType']),
        supplier: _text(json['Orsupplier']),
      );
}

class QtyCheckDetails {
  const QtyCheckDetails({
    required this.purchases,
    required this.sales,
    required this.monthly,
    required this.history,
  });

  final List<PurchaseDetail> purchases;
  final List<SalesDetail> sales;
  final List<MonthlyStat> monthly;
  final List<OrderHistoryEntry> history;
}

List<Map<String, dynamic>> _maps(Object? value) => (value as List? ?? const [])
    .whereType<Map<String, dynamic>>()
    .toList(growable: false);

String? _text(Object? value) {
  if (value == null) return null;
  final text = value.toString().trim();
  return text.isEmpty ? null : text;
}

int? _integer(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '');
}

num? _number(Object? value) {
  if (value is num) return value;
  return num.tryParse(value?.toString() ?? '');
}

DateTime? _date(Object? value) {
  final text = _text(value);
  return text == null ? null : DateTime.tryParse(text);
}

bool _bool(Object? value, {bool fallback = false}) {
  if (value is bool) return value;
  if (value is num) return value != 0;
  return switch (value?.toString().toLowerCase()) {
    'true' || '1' || 'yes' => true,
    'false' || '0' || 'no' => false,
    _ => fallback,
  };
}
