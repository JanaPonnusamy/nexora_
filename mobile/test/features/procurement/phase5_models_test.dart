import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/features/procurement/domain/purchase_workspace_models.dart';
import 'package:nexora_mobile/features/procurement/domain/refresh_compare_models.dart';
import 'package:nexora_mobile/features/procurement/domain/stock_distribution_models.dart';

PurchaseWorkspaceItem _item(String code, double qty,
        {String status = 'review'}) =>
    PurchaseWorkspaceItem(
      orderItemId: 'item-$code',
      productCode: code,
      productName: 'Product $code',
      suggestedQty: qty,
      finalQty: qty,
      assignedQty: 0,
      remainingQty: qty,
      status: status,
    );

void main() {
  test('final-order comparison classifies every change type', () {
    final rows = compareFinalOrders(
      [_item('same', 2), _item('up', 2), _item('down', 4), _item('gone', 1)],
      [_item('same', 2), _item('up', 5), _item('down', 1), _item('new', 3)],
    );
    final byCode = {for (final row in rows) row.productCode: row};

    expect(byCode['same']!.change, RefreshChangeType.unchanged);
    expect(byCode['up']!.change, RefreshChangeType.increased);
    expect(byCode['up']!.difference, 3);
    expect(byCode['down']!.change, RefreshChangeType.decreased);
    expect(byCode['gone']!.change, RefreshChangeType.removed);
    expect(byCode['new']!.change, RefreshChangeType.added);
  });

  test('comparison retains skipped state from either refresh', () {
    final row = compareFinalOrders(
      [_item('42', 2, status: 'skipped')],
      [_item('42', 2)],
    ).single;

    expect(row.sourceSkipped, isTrue);
    expect(row.targetSkipped, isFalse);
  });

  test('distribution target reports missing supplier mapping', () {
    final target = DistributionTarget.fromJson({
      'store_id': 'store-1',
      'store_code': 'NMS',
      'store_name': 'Nathan Medicals',
      'enabled': 1,
      'local_supplier_code': null,
    });

    expect(target.enabled, isTrue);
    expect(target.ready, isFalse);
  });

  test('distribution run parses stringified SQL values', () {
    final run = DistributionRun.fromJson({
      'run_id': 'run-1',
      'source_store_code': 'NMW',
      'status': 'completed',
      'stores_total': '4',
      'stores_succeeded': 3,
      'stores_failed': '1',
      'total_products': '812',
      'total_stock_qty': '1942.5',
      'started_at': '2026-08-19T10:30:00',
    });

    expect(run.storesTotal, 4);
    expect(run.storesFailed, 1);
    expect(run.totalStockQty, 1942.5);
    expect(run.startedAt, DateTime.parse('2026-08-19T10:30:00'));
  });

  test('distribution detail parses independent stage statuses', () {
    final detail = DistributionRunDetail.fromJson({
      'run': {
        'run_id': 'run-1',
        'source_store_code': 'NMW',
        'status': 'completed',
      },
      'items': [
        {
          'run_item_id': 'item-1',
          'store_code': 'NMS',
          'status': 'failed',
          'stock_status': 'success',
          'excel_status': 'success',
          'whatsapp_status': 'failed',
          'rows_exported': 200,
        },
      ],
    });

    expect(detail.items.single.stockStatus, 'success');
    expect(detail.items.single.whatsappStatus, 'failed');
  });
}
