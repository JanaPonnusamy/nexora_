/// Platform-wide sync KPIs, as returned by `GET /api/sync/control-center`.
/// The same shape backs the HO web console's Sync Control Center dashboard.
class SyncKpis {
  const SyncKpis({
    this.storesOnline = 0,
    this.storesOffline = 0,
    this.syncRunning = 0,
    this.queued = 0,
    this.completedToday = 0,
    this.failedToday = 0,
  });

  final int storesOnline;
  final int storesOffline;
  final int syncRunning;
  final int queued;
  final int completedToday;
  final int failedToday;

  int get totalStores => storesOnline + storesOffline;

  factory SyncKpis.fromJson(Map<String, dynamic> json) => SyncKpis(
        storesOnline: _asInt(json['stores_online']),
        storesOffline: _asInt(json['stores_offline']),
        syncRunning: _asInt(json['sync_running']),
        queued: _asInt(json['queued']),
        completedToday: _asInt(json['completed_today']),
        failedToday: _asInt(json['failed_today']),
      );
}

/// One store's row in the Sync Control Center grid.
class StoreSyncStatus {
  const StoreSyncStatus({
    required this.storeId,
    required this.storeCode,
    required this.storeName,
    required this.connectionType,
    required this.agentStatus,
    required this.currentActivity,
    required this.isSyncing,
    required this.status,
    this.lastSync,
  });

  final String storeId;
  final String storeCode;
  final String storeName;
  final String connectionType;

  /// `Online` or `Offline` — derived server-side from the agent heartbeat.
  final String agentStatus;

  /// `Syncing` or `Idle`.
  final String currentActivity;
  final bool isSyncing;

  /// `Syncing`, `Online`, or `Offline` — the single label the desktop grid
  /// shows (syncing takes precedence over connection state).
  final String status;
  final DateTime? lastSync;

  bool get isOnline => agentStatus == 'Online';

  factory StoreSyncStatus.fromJson(Map<String, dynamic> json) {
    return StoreSyncStatus(
      storeId: json['store_id']?.toString() ?? '',
      storeCode: json['store_code']?.toString() ?? '',
      storeName: json['store_name']?.toString() ?? '',
      connectionType: json['connection_type']?.toString() ?? 'Offline',
      agentStatus: json['agent_status']?.toString() ?? 'Offline',
      currentActivity: json['current_activity']?.toString() ?? 'Idle',
      isSyncing: json['is_syncing'] == true,
      status: json['status']?.toString() ?? 'Offline',
      lastSync: _asDateOrNull(json['last_sync']),
    );
  }
}

/// The full `control-center` response: platform KPIs + every active store.
class SyncControlCenter {
  const SyncControlCenter({required this.kpis, required this.stores});

  final SyncKpis kpis;
  final List<StoreSyncStatus> stores;

  factory SyncControlCenter.fromJson(Map<String, dynamic> json) {
    final rawStores = json['stores'];
    return SyncControlCenter(
      kpis: SyncKpis.fromJson(
        (json['kpis'] as Map?)?.cast<String, dynamic>() ?? const {},
      ),
      stores: rawStores is List
          ? rawStores
              .whereType<Map>()
              .map((m) => StoreSyncStatus.fromJson(m.cast<String, dynamic>()))
              .toList(growable: false)
          : const [],
    );
  }
}

int _asInt(Object? v) {
  if (v == null) return 0;
  if (v is int) return v;
  if (v is num) return v.toInt();
  return int.tryParse(v.toString()) ?? 0;
}

DateTime? _asDateOrNull(Object? v) {
  if (v == null) return null;
  return DateTime.tryParse(v.toString());
}
