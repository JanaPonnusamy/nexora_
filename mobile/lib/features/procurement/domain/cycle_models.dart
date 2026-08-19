/// Models for `/api/procurement/cycles` and `/refreshes`.
///
/// Field names were read off a live response, not inferred from the router —
/// the cycle row carries `cycle_id`/`active_refresh_id` and nullable GRN and
/// sale-bill numbers that the console has to render as "not stamped yet"
/// rather than as zero.
library;

/// Where a cycle is in its life. The server sends free text, so an unknown
/// value is carried through and shown rather than collapsed to a default — a
/// status this build has not heard of is information, not an error.
enum CycleStatus {
  active,
  closed,
  draft,
  unknown;

  static CycleStatus fromWire(String? value) => switch (value?.toUpperCase()) {
        'ACTIVE' => CycleStatus.active,
        'CLOSED' => CycleStatus.closed,
        'DRAFT' => CycleStatus.draft,
        _ => CycleStatus.unknown,
      };

  bool get isOpen => this == CycleStatus.active;
}

class ProcurementCycle {
  const ProcurementCycle({
    required this.cycleId,
    required this.name,
    required this.status,
    required this.rawStatus,
    this.storeId,
    this.description,
    this.startGrnNumber,
    this.startSaleBillNumber,
    this.endGrnNumber,
    this.endSaleBillNumber,
    this.activeRefreshId,
    this.createdAt,
    this.updatedAt,
  });

  final String cycleId;
  final String name;
  final CycleStatus status;

  /// What the server actually said, for statuses this build does not know.
  final String rawStatus;

  final String? storeId;
  final String? description;

  /// Counter readings the cycle opened at. Null until stamped; the console
  /// must not render that as 0, which would read as a real reading.
  final String? startGrnNumber;
  final String? startSaleBillNumber;
  final String? endGrnNumber;
  final String? endSaleBillNumber;

  /// The refresh currently being worked. Null on a cycle that has none yet,
  /// which is the state the console offers "Start a refresh" from.
  final String? activeRefreshId;

  final DateTime? createdAt;
  final DateTime? updatedAt;

  bool get hasActiveRefresh => activeRefreshId != null;

  /// True once both closing counters are stamped — the cycle has been
  /// reconciled even if the status has not caught up.
  bool get isReconciled => endGrnNumber != null && endSaleBillNumber != null;

  factory ProcurementCycle.fromJson(Map<String, dynamic> json) {
    String? text(String key) {
      final value = json[key];
      if (value == null) return null;
      final s = value.toString().trim();
      return s.isEmpty ? null : s;
    }

    return ProcurementCycle(
      cycleId: text('cycle_id') ?? '',
      name: text('name') ?? 'Untitled cycle',
      status: CycleStatus.fromWire(text('status')),
      rawStatus: text('status') ?? '',
      storeId: text('store_id'),
      description: text('description'),
      startGrnNumber: text('start_grn_number'),
      startSaleBillNumber: text('start_sale_bill_number'),
      endGrnNumber: text('end_grn_number'),
      endSaleBillNumber: text('end_sale_bill_number'),
      activeRefreshId: text('active_refresh_id'),
      createdAt: _parseDate(text('created_at')),
      updatedAt: _parseDate(text('updated_at')),
    );
  }
}

/// One page of cycles.
class CyclePage {
  const CyclePage({
    required this.items,
    required this.total,
    required this.page,
    required this.pageSize,
  });

  final List<ProcurementCycle> items;
  final int total;
  final int page;
  final int pageSize;

  bool get hasMore => page * pageSize < total;

  factory CyclePage.fromJson(Map<String, dynamic> json) => CyclePage(
        items: (json['items'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(ProcurementCycle.fromJson)
            .toList(growable: false),
        total: _parseInt(json['total']) ?? 0,
        page: _parseInt(json['page']) ?? 1,
        pageSize: _parseInt(json['page_size']) ?? 20,
      );
}

/// The answer to a close request.
///
/// `close_cycle` returns `status='pending_confirm'` when items remain and
/// `force` was not set. That is a question, not a failure, and the console has
/// to be able to tell the two apart — otherwise it either shows an error for a
/// normal prompt, or forces past a check nobody agreed to.
class CloseOutcome {
  const CloseOutcome({
    required this.status,
    this.message,
    this.pendingCount,
  });

  final String status;
  final String? message;
  final int? pendingCount;

  bool get needsConfirmation => status == 'pending_confirm';
  bool get closed => !needsConfirmation;

  factory CloseOutcome.fromJson(Map<String, dynamic> json) => CloseOutcome(
        status: json['status']?.toString() ?? 'closed',
        message: json['message']?.toString() ?? json['detail']?.toString(),
        pendingCount: _parseInt(json['pending_count'] ?? json['pending']),
      );
}

DateTime? _parseDate(String? value) =>
    value == null ? null : DateTime.tryParse(value);

int? _parseInt(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}
