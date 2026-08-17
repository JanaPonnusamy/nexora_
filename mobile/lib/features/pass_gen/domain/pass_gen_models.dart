/// Models for `/api/pass-gen/*`.
///
/// Pass Gen mints the legacy 14-character store passcodes the field ordering
/// app consumes — it is **not** a gate pass, despite the name. Every endpoint
/// spans all tenants by design (platform-ops tooling), which is why the server
/// restricts it to unrestricted-scope users and the client must gate the whole
/// screen on `isPlatformUser`.
library;

/// A store and the two-digit numeric code it uses inside a passcode.
class PassGenStore {
  const PassGenStore({
    required this.storeId,
    required this.tenantId,
    required this.storeCode,
    this.storeName,
    this.numericCode,
  });

  final String storeId;
  final String tenantId;
  final String storeCode;
  final String? storeName;

  /// 0..99, or null when the store has never been mapped. A store with no
  /// numeric code **cannot** produce a passcode — the server skips it.
  final int? numericCode;

  factory PassGenStore.fromJson(Map<String, dynamic> json) => PassGenStore(
        storeId: json['store_id']?.toString() ?? '',
        tenantId: json['tenant_id']?.toString() ?? '',
        storeCode: json['store_code']?.toString() ?? '',
        storeName: json['store_name']?.toString(),
        numericCode: switch (json['numeric_code']) {
          final int i => i,
          final num n => n.toInt(),
          final String s => int.tryParse(s),
          _ => null,
        },
      );

  bool get isMapped => numericCode != null;

  String get label =>
      (storeName?.trim().isNotEmpty ?? false) ? storeName!.trim() : storeCode;
}

/// One generated passcode.
class PassGenResult {
  const PassGenResult({
    required this.storeId,
    required this.storeCode,
    required this.numericCode,
    required this.passcode,
    this.storeName,
  });

  final String storeId;
  final String storeCode;
  final int numericCode;
  final String passcode;
  final String? storeName;

  factory PassGenResult.fromJson(Map<String, dynamic> json) => PassGenResult(
        storeId: json['store_id']?.toString() ?? '',
        storeCode: json['store_code']?.toString() ?? '',
        numericCode: switch (json['numeric_code']) {
          final int i => i,
          final num n => n.toInt(),
          _ => 0,
        },
        passcode: json['passcode']?.toString() ?? '',
        storeName: json['store_name']?.toString(),
      );

  String get label =>
      (storeName?.trim().isNotEmpty ?? false) ? storeName!.trim() : storeCode;
}

/// The result of one generation row: what it produced, and what it could not.
class PassGenRowResult {
  const PassGenRowResult({
    required this.rowId,
    this.results = const [],
    this.skipped = const [],
  });

  final String rowId;
  final List<PassGenResult> results;

  /// Store codes with no numeric mapping. Surfacing these matters: without
  /// them a user who selected ten stores and got seven passcodes has no way to
  /// tell whether the tool failed or three stores were simply unmapped.
  final List<String> skipped;

  factory PassGenRowResult.fromJson(Map<String, dynamic> json) =>
      PassGenRowResult(
        rowId: json['row_id']?.toString() ?? '',
        results: (json['results'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(PassGenResult.fromJson)
            .toList(growable: false),
        skipped: (json['skipped'] as List? ?? const [])
            .map((e) => e.toString())
            .toList(growable: false),
      );
}

/// The inputs for one generation.
///
/// The desktop tool batches several day-range rows into one request. Mobile
/// sends a single row: the field job is "mint a code for these stores now",
/// and a multi-row batch editor on a phone is a form nobody completes without
/// mistakes. The wire format still carries a rows array, so adding batching
/// later needs no server change.
class PassGenRequest {
  const PassGenRequest({
    required this.orderNo,
    required this.targetDate,
    required this.minDays,
    required this.maxDays,
    this.storeIds = const [],
    this.orderYes = false,
    this.compareLastOrder = false,
  });

  /// 0..9, shared by every row of a generation.
  final int orderNo;

  final DateTime targetDate;

  /// Day window encoded into the passcode. Both are base-36 two-digit fields
  /// server-side, hence the 1295 ceiling.
  final int minDays;
  final int maxDays;

  /// Empty means every mapped store.
  final List<String> storeIds;

  final bool orderYes;
  final bool compareLastOrder;

  /// Matches `MAX_BASE36_2` in `backend/modules/pass_gen/passcode.py`
  /// (36² − 1). Sending more is a 422, not a clamped value.
  static const int maxDays_ = 36 * 36 - 1;

  static const int maxOrderNo = 9;

  /// True when the server would accept this as-is.
  bool get isValid =>
      orderNo >= 0 &&
      orderNo <= maxOrderNo &&
      minDays >= 0 &&
      minDays <= maxDays_ &&
      maxDays >= 0 &&
      maxDays <= maxDays_ &&
      minDays <= maxDays;

  /// Why it is not valid, for the button's disabled reason.
  String? get problem {
    if (orderNo < 0 || orderNo > maxOrderNo) {
      return 'Order No must be 0–9.';
    }
    if (minDays < 0 || minDays > maxDays_) {
      return 'Min days must be 0–$maxDays_.';
    }
    if (maxDays < 0 || maxDays > maxDays_) {
      return 'Max days must be 0–$maxDays_.';
    }
    if (minDays > maxDays) {
      return 'Min days cannot exceed max days.';
    }
    return null;
  }

  Map<String, dynamic> toJson() => {
        'order_no': orderNo,
        'target_date': _date(targetDate),
        'rows': [
          {
            // The server only uses row_id to correlate results back to rows;
            // with a single row a stable literal is enough.
            'row_id': 'mobile',
            'store_ids': storeIds,
            'min_days': minDays,
            'max_days': maxDays,
            'order_yes': orderYes ? 1 : 0,
            'compare_last_order': compareLastOrder ? 1 : 0,
          },
        ],
      };

  PassGenRequest copyWith({
    int? orderNo,
    DateTime? targetDate,
    int? minDays,
    int? maxDays,
    List<String>? storeIds,
    bool? orderYes,
    bool? compareLastOrder,
  }) =>
      PassGenRequest(
        orderNo: orderNo ?? this.orderNo,
        targetDate: targetDate ?? this.targetDate,
        minDays: minDays ?? this.minDays,
        maxDays: maxDays ?? this.maxDays,
        storeIds: storeIds ?? this.storeIds,
        orderYes: orderYes ?? this.orderYes,
        compareLastOrder: compareLastOrder ?? this.compareLastOrder,
      );

  static String _date(DateTime d) => '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';
}
