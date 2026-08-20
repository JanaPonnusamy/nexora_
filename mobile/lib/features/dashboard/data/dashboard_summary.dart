/// Models for `GET /api/mobile/v1/dashboard`.
///
/// Every section is nullable by design: the server builds each independently
/// and returns null for one whose tables are not provisioned yet, so a missing
/// module degrades a single card instead of blanking the screen.
library;

int _asInt(Object? v) => switch (v) {
      final int i => i,
      final num n => n.toInt(),
      final String s => int.tryParse(s) ?? 0,
      _ => 0,
    };

bool _asBool(Object? v) => switch (v) {
      final bool b => b,
      final num n => n != 0,
      final String s => s.toLowerCase() == 'true',
      _ => false,
    };

DateTime? _asDate(Object? v) =>
    v is String && v.isNotEmpty ? DateTime.tryParse(v) : null;

class DashboardUser {
  const DashboardUser({
    required this.userId,
    required this.username,
    this.firstName,
    this.isPlatformUser = false,
    this.moduleCount = 0,
  });

  final String userId;
  final String username;
  final String? firstName;
  final bool isPlatformUser;
  final int moduleCount;

  String get displayName => (firstName != null && firstName!.trim().isNotEmpty)
      ? firstName!.trim()
      : username;

  factory DashboardUser.fromJson(Map<String, dynamic> json) => DashboardUser(
        userId: json['user_id']?.toString() ?? '',
        username: json['username']?.toString() ?? '',
        firstName: json['first_name']?.toString(),
        isPlatformUser: _asBool(json['is_platform_user']),
        moduleCount: _asInt(json['module_count']),
      );
}

class DashboardStore {
  const DashboardStore({
    required this.storeId,
    required this.storeCode,
    required this.storeName,
    this.agentOnline = false,
    this.lastSyncTime,
    this.lastSyncStatus,
    this.agentVersion,
  });

  final String storeId;
  final String storeCode;
  final String storeName;
  final bool agentOnline;
  final DateTime? lastSyncTime;
  final String? lastSyncStatus;
  final String? agentVersion;

  factory DashboardStore.fromJson(Map<String, dynamic> json) => DashboardStore(
        storeId: json['store_id']?.toString() ?? '',
        storeCode: json['store_code']?.toString() ?? '',
        storeName: json['store_name']?.toString() ?? '',
        agentOnline: _asBool(json['agent_online']),
        lastSyncTime: _asDate(json['last_sync_time']),
        lastSyncStatus: json['last_sync_status']?.toString(),
        agentVersion: json['agent_version']?.toString(),
      );
}

class DashboardSync {
  const DashboardSync({
    this.storesOnline = 0,
    this.storesOffline = 0,
    this.storesTotal = 0,
    this.runningForStore = 0,
  });

  final int storesOnline;
  final int storesOffline;
  final int storesTotal;
  final int runningForStore;

  factory DashboardSync.fromJson(Map<String, dynamic> json) => DashboardSync(
        storesOnline: _asInt(json['stores_online']),
        storesOffline: _asInt(json['stores_offline']),
        storesTotal: _asInt(json['stores_total']),
        runningForStore: _asInt(json['running_for_store']),
      );
}

class DashboardDocuments {
  const DashboardDocuments({
    this.awaitingReview = 0,
    this.failed = 0,
    this.processing = 0,
  });

  final int awaitingReview;
  final int failed;
  final int processing;

  factory DashboardDocuments.fromJson(Map<String, dynamic> json) =>
      DashboardDocuments(
        awaitingReview: _asInt(json['awaiting_review']),
        failed: _asInt(json['failed']),
        processing: _asInt(json['processing']),
      );
}

class DashboardProcurement {
  const DashboardProcurement({
    this.cycleNo,
    this.cycleStatus,
    this.pendingReview = 0,
  });

  final int? cycleNo;
  final String? cycleStatus;
  final int pendingReview;

  bool get hasActiveCycle => cycleNo != null;

  factory DashboardProcurement.fromJson(Map<String, dynamic> json) {
    final cycle = json['active_cycle'];
    final map = cycle is Map<String, dynamic> ? cycle : const {};
    return DashboardProcurement(
      cycleNo: map['cycle_no'] is num ? _asInt(map['cycle_no']) : null,
      cycleStatus: map['status']?.toString(),
      pendingReview: _asInt(json['pending_review']),
    );
  }
}

class DashboardSummary {
  const DashboardSummary({
    required this.user,
    this.store,
    this.sync,
    this.documents,
    this.procurement,
    this.generatedAt,
  });

  final DashboardUser user;
  final DashboardStore? store;
  final DashboardSync? sync;
  final DashboardDocuments? documents;
  final DashboardProcurement? procurement;
  final DateTime? generatedAt;

  static Map<String, dynamic>? _section(Object? v) =>
      v is Map<String, dynamic> ? v : null;

  factory DashboardSummary.fromJson(Map<String, dynamic> json) {
    final store = _section(json['store']);
    final sync = _section(json['sync']);
    final documents = _section(json['documents']);
    final procurement = _section(json['procurement']);

    return DashboardSummary(
      user: DashboardUser.fromJson(_section(json['user']) ?? const {}),
      store: store == null ? null : DashboardStore.fromJson(store),
      sync: sync == null ? null : DashboardSync.fromJson(sync),
      documents:
          documents == null ? null : DashboardDocuments.fromJson(documents),
      procurement: procurement == null
          ? null
          : DashboardProcurement.fromJson(procurement),
      generatedAt: _asDate(json['generated_at']),
    );
  }
}
