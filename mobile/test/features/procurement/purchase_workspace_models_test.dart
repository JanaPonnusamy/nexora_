import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/features/procurement/domain/purchase_workspace_models.dart';

Map<String, dynamic> _row({
  Object? finalQty = '12.000',
  Object? assignedQty = 4,
  Object? remainingQty = '8',
  String status = 'partial',
}) =>
    {
      'order_item_id': 'order-1',
      'product_code': '10042',
      'product_name': 'Paracetamol 500mg',
      'suggested_qty': '10.5',
      'final_qty': finalQty,
      'assigned_qty': assignedQty,
      'remaining_qty': remainingQty,
      'item_status': status,
      'movement_class': 'FAST',
      'stock_status': 'LOW',
      'unit_description': '10 TAB',
      'pack': '10',
    };

void main() {
  group('PurchaseWorkspaceItem', () {
    test('parses SQL numeric strings and the reduced mobile fields', () {
      final item = PurchaseWorkspaceItem.fromJson(_row());

      expect(item.orderItemId, 'order-1');
      expect(item.productName, 'Paracetamol 500mg');
      expect(item.suggestedQty, 10.5);
      expect(item.finalQty, 12);
      expect(item.assignedQty, 4);
      expect(item.remainingQty, 8);
      expect(item.canAssign, isTrue);
    });

    test('skipped and fully assigned rows cannot be assigned again', () {
      expect(
        PurchaseWorkspaceItem.fromJson(_row(status: 'skipped')).canAssign,
        isFalse,
      );
      expect(
        PurchaseWorkspaceItem.fromJson(
          _row(assignedQty: 12, remainingQty: 0),
        ).canAssign,
        isFalse,
      );
    });

    test('missing values produce a safe renderable item', () {
      final item = PurchaseWorkspaceItem.fromJson(const {});

      expect(item.productName, 'Unnamed product');
      expect(item.finalQty, 0);
      expect(item.status, 'pending');
    });
  });

  test('PurchaseWorkspacePage accepts ordinary decoded JSON maps', () {
    final page = PurchaseWorkspacePage.fromJson({
      'items': [_row(), _row()],
      'total': '81',
      'page': 1,
      'page_size': 50,
    });

    expect(page.items, hasLength(2));
    expect(page.total, 81);
    expect(page.pageSize, 50);
  });

  test('PurchaseSupplier falls back to code when the name is absent', () {
    final supplier = PurchaseSupplier.fromJson({
      'supplier_code': 'SUP-9',
      'supplier_name': null,
    });

    expect(supplier.code, 'SUP-9');
    expect(supplier.name, 'SUP-9');
  });
}
