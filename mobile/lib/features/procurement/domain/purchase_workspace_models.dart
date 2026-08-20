library;

double _number(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '') ?? 0;
}

String? _text(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? null : text;
}

class PurchaseWorkspaceItem {
  const PurchaseWorkspaceItem({
    required this.orderItemId,
    required this.productCode,
    required this.productName,
    required this.suggestedQty,
    required this.finalQty,
    required this.assignedQty,
    required this.remainingQty,
    required this.status,
    this.movementClass,
    this.stockStatus,
    this.unitDescription,
    this.pack,
  });

  final String orderItemId;
  final String productCode;
  final String productName;
  final double suggestedQty;
  final double finalQty;
  final double assignedQty;
  final double remainingQty;
  final String status;
  final String? movementClass;
  final String? stockStatus;
  final String? unitDescription;
  final String? pack;

  bool get canAssign => status != 'skipped' && remainingQty > 0;

  factory PurchaseWorkspaceItem.fromJson(Map<String, dynamic> json) =>
      PurchaseWorkspaceItem(
        orderItemId: _text(json['order_item_id']) ?? '',
        productCode: _text(json['product_code']) ?? '',
        productName: _text(json['product_name']) ?? 'Unnamed product',
        suggestedQty: _number(json['suggested_qty']),
        finalQty: _number(json['final_qty']),
        assignedQty: _number(json['assigned_qty']),
        remainingQty: _number(json['remaining_qty']),
        status: (_text(json['item_status']) ?? 'pending').toLowerCase(),
        movementClass: _text(json['movement_class']),
        stockStatus: _text(json['stock_status']),
        unitDescription: _text(json['unit_description']),
        pack: _text(json['pack']),
      );

  PurchaseWorkspaceItem copyWith({
    double? finalQty,
    double? assignedQty,
    double? remainingQty,
    String? status,
  }) =>
      PurchaseWorkspaceItem(
        orderItemId: orderItemId,
        productCode: productCode,
        productName: productName,
        suggestedQty: suggestedQty,
        finalQty: finalQty ?? this.finalQty,
        assignedQty: assignedQty ?? this.assignedQty,
        remainingQty: remainingQty ?? this.remainingQty,
        status: status ?? this.status,
        movementClass: movementClass,
        stockStatus: stockStatus,
        unitDescription: unitDescription,
        pack: pack,
      );
}

class PurchaseWorkspacePage {
  const PurchaseWorkspacePage({
    required this.items,
    required this.total,
    required this.page,
    required this.pageSize,
  });

  final List<PurchaseWorkspaceItem> items;
  final int total;
  final int page;
  final int pageSize;

  factory PurchaseWorkspacePage.fromJson(Map<String, dynamic> json) =>
      PurchaseWorkspacePage(
        items: (json['items'] as List? ?? const [])
            .whereType<Map>()
            .map((row) =>
                PurchaseWorkspaceItem.fromJson(row.cast<String, dynamic>()))
            .toList(growable: false),
        total: _number(json['total']).toInt(),
        page: _number(json['page']).toInt().clamp(1, 1 << 31),
        pageSize: _number(json['page_size']).toInt(),
      );
}

class PurchaseSupplier {
  const PurchaseSupplier({required this.code, required this.name});

  final String code;
  final String name;

  factory PurchaseSupplier.fromJson(Map<String, dynamic> json) =>
      PurchaseSupplier(
        code: _text(json['supplier_code'] ?? json['code']) ?? '',
        name: _text(json['supplier_name'] ?? json['name']) ??
            _text(json['supplier_code'] ?? json['code']) ??
            'Unnamed supplier',
      );
}
