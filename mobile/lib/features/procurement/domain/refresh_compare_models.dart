import 'package:nexora_mobile/features/procurement/domain/purchase_workspace_models.dart';

String? _text(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? null : text;
}

int _integer(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

class ProcurementRefresh {
  const ProcurementRefresh({
    required this.refreshId,
    required this.cycleId,
    required this.name,
    required this.number,
    required this.status,
  });

  final String refreshId;
  final String cycleId;
  final String name;
  final int number;
  final String status;

  String get label => number > 0 ? 'Refresh $number' : name;

  factory ProcurementRefresh.fromJson(Map<String, dynamic> json) =>
      ProcurementRefresh(
        refreshId: _text(json['refresh_id']) ?? '',
        cycleId: _text(json['cycle_id']) ?? '',
        name: _text(json['snapshot_name']) ?? 'Unnamed refresh',
        number: _integer(json['refresh_no']),
        status: _text(json['snapshot_status']) ?? 'Unknown',
      );
}

enum RefreshChangeType {
  added,
  removed,
  increased,
  decreased,
  unchanged;

  String get label => switch (this) {
        RefreshChangeType.added => 'Added',
        RefreshChangeType.removed => 'Removed',
        RefreshChangeType.increased => 'Increased',
        RefreshChangeType.decreased => 'Decreased',
        RefreshChangeType.unchanged => 'No change',
      };
}

class RefreshCompareRow {
  const RefreshCompareRow({
    required this.productCode,
    required this.productName,
    required this.sourceQty,
    required this.targetQty,
    required this.sourceSkipped,
    required this.targetSkipped,
    required this.change,
  });

  final String productCode;
  final String productName;
  final double sourceQty;
  final double targetQty;
  final bool sourceSkipped;
  final bool targetSkipped;
  final RefreshChangeType change;

  double get difference => targetQty - sourceQty;
}

List<RefreshCompareRow> compareFinalOrders(
  Iterable<PurchaseWorkspaceItem> source,
  Iterable<PurchaseWorkspaceItem> target,
) {
  final before = {for (final item in source) item.productCode: item};
  final after = {for (final item in target) item.productCode: item};
  final codes =
      {...before.keys, ...after.keys}.where((code) => code.isNotEmpty);
  final rows = <RefreshCompareRow>[];
  for (final code in codes) {
    final from = before[code];
    final to = after[code];
    final fromQty = from?.finalQty ?? 0;
    final toQty = to?.finalQty ?? 0;
    final change = from == null
        ? RefreshChangeType.added
        : to == null
            ? RefreshChangeType.removed
            : toQty > fromQty
                ? RefreshChangeType.increased
                : toQty < fromQty
                    ? RefreshChangeType.decreased
                    : RefreshChangeType.unchanged;
    rows.add(RefreshCompareRow(
      productCode: code,
      productName: to?.productName ?? from?.productName ?? code,
      sourceQty: fromQty,
      targetQty: toQty,
      sourceSkipped: from?.status == 'skipped',
      targetSkipped: to?.status == 'skipped',
      change: change,
    ));
  }
  rows.sort((a, b) => a.productName.compareTo(b.productName));
  return rows;
}
