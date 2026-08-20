import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/outbox_providers.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/procurement/application/cycle_providers.dart';
import 'package:nexora_mobile/features/procurement/data/purchase_workspace_api.dart';
import 'package:nexora_mobile/features/procurement/domain/purchase_workspace_models.dart';

final purchaseWorkspaceApiProvider = Provider<PurchaseWorkspaceApi>(
  (ref) => PurchaseWorkspaceApi(ref.watch(dioProvider)),
);

class PurchaseWorkspaceContext {
  const PurchaseWorkspaceContext({
    required this.tenantId,
    required this.storeId,
    required this.refreshId,
  });

  final String tenantId;
  final String storeId;
  final String refreshId;
}

/// The newest active cycle with a working refresh for the selected store.
final purchaseWorkspaceContextProvider =
    FutureProvider.autoDispose<PurchaseWorkspaceContext?>((ref) async {
  final scope = ref.watch(cycleScopeProvider);
  if (scope == null) return null;
  final cycles = await ref.watch(cycleApiProvider).cycles(
        tenantId: scope.tenantId,
        storeId: scope.storeId,
        status: 'ACTIVE',
      );
  for (final cycle in cycles.items) {
    final refreshId = cycle.activeRefreshId;
    if (refreshId != null && refreshId.isNotEmpty) {
      return PurchaseWorkspaceContext(
        tenantId: scope.tenantId,
        storeId: scope.storeId,
        refreshId: refreshId,
      );
    }
  }
  return null;
});

class PurchaseWorkspaceData {
  const PurchaseWorkspaceData({required this.context, required this.page});

  final PurchaseWorkspaceContext context;
  final PurchaseWorkspacePage page;
}

final purchaseWorkspaceProvider = FutureProvider.autoDispose
    .family<PurchaseWorkspaceData?, String>((ref, search) async {
  final context = await ref.watch(purchaseWorkspaceContextProvider.future);
  if (context == null) return null;
  final page = await ref.watch(purchaseWorkspaceApiProvider).workspace(
        tenantId: context.tenantId,
        refreshId: context.refreshId,
        search: search,
      );
  return PurchaseWorkspaceData(context: context, page: page);
});

class PurchaseOutboxKinds {
  PurchaseOutboxKinds._();

  static const finalQty = 'procurement.finalQty';
  static const assign = 'procurement.assign';
  static const skip = 'procurement.skip';
  static const restore = 'procurement.restore';
}

String purchaseItemScope(String orderItemId) => 'purchase-item:$orderItemId';

class PurchaseActionResult {
  const PurchaseActionResult(this.message, {this.item, this.queued = false});
  const PurchaseActionResult.failed(this.message)
      : item = null,
        queued = false;

  final String message;
  final PurchaseWorkspaceItem? item;
  final bool queued;
  bool get ok => item != null || queued;
}

final purchaseWorkspaceControllerProvider =
    Provider<PurchaseWorkspaceController>(PurchaseWorkspaceController.new);

class PurchaseWorkspaceController {
  PurchaseWorkspaceController(this._ref);

  final Ref _ref;

  PurchaseWorkspaceApi get _api => _ref.read(purchaseWorkspaceApiProvider);
  String? get _actor => _ref.read(cycleActorProvider);

  Future<PurchaseActionResult> setFinalQty({
    required PurchaseWorkspaceContext context,
    required PurchaseWorkspaceItem item,
    required double qty,
  }) async {
    if (qty < item.assignedQty) {
      return PurchaseActionResult.failed(
        'Quantity cannot be below ${item.assignedQty.g} already assigned.',
      );
    }
    try {
      final updated = await _api.setFinalQty(
        tenantId: context.tenantId,
        orderItemId: item.orderItemId,
        finalQty: qty,
        actor: _actor,
      );
      return PurchaseActionResult('Final quantity updated.', item: updated);
    } on ApiException catch (error) {
      if (!error.isNetwork) return PurchaseActionResult.failed(error.message);
      await _ref.read(outboxRepositoryProvider).enqueue(
            kind: PurchaseOutboxKinds.finalQty,
            scope: purchaseItemScope(item.orderItemId),
            payload: {
              'tenantId': context.tenantId,
              'orderItemId': item.orderItemId,
              'finalQty': qty,
              'actor': _actor,
            },
            summary: 'Final quantity for ${item.productName}',
          );
      return PurchaseActionResult(
        'Saved on this device. It will sync when you are online.',
        item: item.copyWith(
          finalQty: qty,
          remainingQty: qty - item.assignedQty,
          status: qty > 0 ? 'review' : item.status,
        ),
        queued: true,
      );
    }
  }

  Future<PurchaseActionResult> assign({
    required PurchaseWorkspaceContext context,
    required PurchaseWorkspaceItem item,
    required PurchaseSupplier supplier,
    required double qty,
  }) async {
    if (qty <= 0 || qty > item.remainingQty) {
      return PurchaseActionResult.failed(
        'Assignment must be between 0 and ${item.remainingQty.g}.',
      );
    }
    try {
      final updated = await _api.assign(
        tenantId: context.tenantId,
        orderItemId: item.orderItemId,
        supplierCode: supplier.code,
        qty: qty,
        actor: _actor,
      );
      return PurchaseActionResult('Assigned to ${supplier.name}.',
          item: updated);
    } on ApiException catch (error) {
      if (!error.isNetwork) return PurchaseActionResult.failed(error.message);
      await _ref.read(outboxRepositoryProvider).enqueue(
            kind: PurchaseOutboxKinds.assign,
            scope: purchaseItemScope(item.orderItemId),
            payload: {
              'tenantId': context.tenantId,
              'orderItemId': item.orderItemId,
              'supplierCode': supplier.code,
              'qty': qty,
              'actor': _actor,
            },
            summary: '${item.productName} assigned to ${supplier.name}',
          );
      return PurchaseActionResult(
        'Assignment saved on this device. It will sync when you are online.',
        item: item.copyWith(
          assignedQty: item.assignedQty + qty,
          remainingQty: item.remainingQty - qty,
          status: item.remainingQty == qty ? 'assigned' : 'partial',
        ),
        queued: true,
      );
    }
  }

  Future<PurchaseActionResult> skip({
    required PurchaseWorkspaceContext context,
    required PurchaseWorkspaceItem item,
    required String reason,
  }) =>
      _statusAction(
        context: context,
        item: item,
        kind: PurchaseOutboxKinds.skip,
        payload: {'reason': reason},
        send: () => _api.skip(
          tenantId: context.tenantId,
          orderItemId: item.orderItemId,
          reason: reason,
          actor: _actor,
        ),
        onlineMessage: 'Product skipped.',
        queuedItem: item.copyWith(status: 'skipped'),
      );

  Future<PurchaseActionResult> restore({
    required PurchaseWorkspaceContext context,
    required PurchaseWorkspaceItem item,
  }) =>
      _statusAction(
        context: context,
        item: item,
        kind: PurchaseOutboxKinds.restore,
        payload: const {},
        send: () => _api.restore(
          tenantId: context.tenantId,
          orderItemId: item.orderItemId,
          actor: _actor,
        ),
        onlineMessage: 'Product restored.',
        queuedItem: item.copyWith(status: 'review'),
      );

  Future<PurchaseActionResult> _statusAction({
    required PurchaseWorkspaceContext context,
    required PurchaseWorkspaceItem item,
    required String kind,
    required Map<String, dynamic> payload,
    required Future<PurchaseWorkspaceItem> Function() send,
    required String onlineMessage,
    required PurchaseWorkspaceItem queuedItem,
  }) async {
    try {
      return PurchaseActionResult(onlineMessage, item: await send());
    } on ApiException catch (error) {
      if (!error.isNetwork) return PurchaseActionResult.failed(error.message);
      await _ref.read(outboxRepositoryProvider).enqueue(
            kind: kind,
            scope: purchaseItemScope(item.orderItemId),
            payload: {
              'tenantId': context.tenantId,
              'orderItemId': item.orderItemId,
              'actor': _actor,
              ...payload,
            },
            summary:
                '${kind == PurchaseOutboxKinds.skip ? 'Skip' : 'Restore'} ${item.productName}',
          );
      return PurchaseActionResult(
        'Saved on this device. It will sync when you are online.',
        item: queuedItem,
        queued: true,
      );
    }
  }
}

/// Registers the persisted mutation kinds before the global outbox starts.
final purchaseOutboxHandlersProvider = Provider<void>((ref) {
  final dispatcher = ref.watch(outboxDispatcherProvider);
  final api = ref.watch(purchaseWorkspaceApiProvider);

  dispatcher.register(PurchaseOutboxKinds.finalQty, (payload) async {
    await api.setFinalQty(
      tenantId: payload['tenantId'] as String,
      orderItemId: payload['orderItemId'] as String,
      finalQty: (payload['finalQty'] as num).toDouble(),
      actor: payload['actor'] as String?,
    );
  });
  dispatcher.register(PurchaseOutboxKinds.assign, (payload) async {
    await api.assign(
      tenantId: payload['tenantId'] as String,
      orderItemId: payload['orderItemId'] as String,
      supplierCode: payload['supplierCode'] as String,
      qty: (payload['qty'] as num).toDouble(),
      actor: payload['actor'] as String?,
    );
  });
  dispatcher.register(PurchaseOutboxKinds.skip, (payload) async {
    await api.skip(
      tenantId: payload['tenantId'] as String,
      orderItemId: payload['orderItemId'] as String,
      reason: payload['reason'] as String,
      actor: payload['actor'] as String?,
    );
  });
  dispatcher.register(PurchaseOutboxKinds.restore, (payload) async {
    await api.restore(
      tenantId: payload['tenantId'] as String,
      orderItemId: payload['orderItemId'] as String,
      actor: payload['actor'] as String?,
    );
  });
});

extension _CompactNumber on double {
  String get g => this == roundToDouble() ? toInt().toString() : toString();
}
