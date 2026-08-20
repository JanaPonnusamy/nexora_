/// Models for the network-wide live sync view.
///
/// Field names mirror `backend/modules/sync/runtime_repository.py`
/// (`get_live_status`) and `backend/controllers/sync_admin_controller.py`
/// exactly. Parsing is defensive on purpose: these payloads are assembled from
/// raw SQL with `ISNULL` defaults and nullable joins, so a missing store name
/// or a null total is normal traffic, not corruption.
library;

int _asInt(Object? v) => switch (v) {
      final int i => i,
      final num n => n.toInt(),
      final String s => int.tryParse(s) ?? 0,
      _ => 0,
    };

int? _asIntOrNull(Object? v) => switch (v) {
      null => null,
      final int i => i,
      final num n => n.toInt(),
      final String s => int.tryParse(s),
      _ => null,
    };

double _asDouble(Object? v) => switch (v) {
      final double d => d,
      final num n => n.toDouble(),
      final String s => double.tryParse(s) ?? 0,
      _ => 0,
    };

DateTime? _asDate(Object? v) =>
    v is String && v.isNotEmpty ? DateTime.tryParse(v) : null;

/// One store's in-flight sync execution, as reported by `GET /api/sync/live`.
///
/// The endpoint returns a bare JSON array of these — only RUNNING and PAUSED
/// executions appear, so an empty list means the network is idle rather than
/// unreachable.
class LiveSyncExecution {
  const LiveSyncExecution({
    required this.storeId,
    required this.executionId,
    required this.status,
    this.storeCode,
    this.storeName,
    this.syncType,
    this.currentTable,
    this.chunkNo,
    this.totalChunks,
    this.rowsProcessed = 0,
    this.totalRows,
    this.rowsRemaining,
    this.executionRowsProcessed = 0,
    this.executionTotalRows,
    this.rowsChanged = 0,
    this.rowsUploaded = 0,
    this.speedRowsSec = 0,
    this.etaSeconds,
    this.progressPct = 0,
    this.startedAt,
  });

  final String storeId;
  final String executionId;

  /// `RUNNING` or `PAUSED` — the only two the query selects.
  final String status;

  final String? storeCode;
  final String? storeName;
  final String? syncType;

  /// Table currently being chunked across, if the agent has reported one.
  final String? currentTable;

  final int? chunkNo;
  final int? totalChunks;

  /// Progress within [currentTable].
  final int rowsProcessed;
  final int? totalRows;
  final int? rowsRemaining;

  /// Progress across the whole execution, which is the number a person
  /// actually wants — a table-level bar restarts at zero on every table.
  final int executionRowsProcessed;
  final int? executionTotalRows;

  final int rowsChanged;
  final int rowsUploaded;
  final double speedRowsSec;
  final int? etaSeconds;

  /// Server-computed percentage for the current table, 0..100.
  final double progressPct;

  final DateTime? startedAt;

  factory LiveSyncExecution.fromJson(Map<String, dynamic> json) =>
      LiveSyncExecution(
        storeId: json['store_id']?.toString() ?? '',
        executionId: json['execution_id']?.toString() ?? '',
        status: json['status']?.toString() ?? 'RUNNING',
        storeCode: json['store_code']?.toString(),
        storeName: json['store_name']?.toString(),
        syncType: json['sync_type']?.toString(),
        currentTable: json['current_table']?.toString(),
        chunkNo: _asIntOrNull(json['chunk_no']),
        totalChunks: _asIntOrNull(json['total_chunks']),
        rowsProcessed: _asInt(json['rows_processed']),
        totalRows: _asIntOrNull(json['total_rows']),
        rowsRemaining: _asIntOrNull(json['rows_remaining']),
        executionRowsProcessed: _asInt(json['execution_rows_processed']),
        executionTotalRows: _asIntOrNull(json['execution_total_rows']),
        rowsChanged: _asInt(json['rows_changed']),
        rowsUploaded: _asInt(json['rows_uploaded']),
        speedRowsSec: _asDouble(json['speed_rows_sec']),
        etaSeconds: _asIntOrNull(json['eta_seconds']),
        progressPct: _asDouble(json['progress_pct']),
        startedAt: _asDate(json['started_at']),
      );

  bool get isPaused => status.toUpperCase() == 'PAUSED';

  String get label => storeName ?? storeCode ?? storeId;

  /// Whole-execution progress as 0..1, or null when the agent has not reported
  /// totals yet — an indeterminate bar is honest, a 0% bar is not.
  double? get executionProgress {
    final total = executionTotalRows;
    if (total == null || total <= 0) return null;
    return (executionRowsProcessed / total).clamp(0.0, 1.0);
  }

  /// Current-table progress as 0..1, or null when totals are unknown.
  double? get tableProgress {
    final total = totalRows;
    if (total == null || total <= 0) return null;
    return (rowsProcessed / total).clamp(0.0, 1.0);
  }

  Duration? get eta =>
      etaSeconds == null ? null : Duration(seconds: etaSeconds!);

  Duration? get elapsed =>
      startedAt == null ? null : DateTime.now().difference(startedAt!);
}

/// A finished (or failed) execution from `GET /api/sync/history`.
class SyncHistoryEntry {
  const SyncHistoryEntry({
    required this.executionId,
    required this.status,
    this.storeId,
    this.storeCode,
    this.storeName,
    this.executionType,
    this.syncMode,
    this.startedAt,
    this.completedAt,
    this.rowsSynced = 0,
    this.tablesSynced = 0,
    this.errorMessage,
  });

  final String executionId;
  final String status;
  final String? storeId;
  final String? storeCode;
  final String? storeName;
  final String? executionType;
  final String? syncMode;
  final DateTime? startedAt;
  final DateTime? completedAt;
  final int rowsSynced;
  final int tablesSynced;
  final String? errorMessage;

  factory SyncHistoryEntry.fromJson(Map<String, dynamic> json) =>
      SyncHistoryEntry(
        executionId: json['execution_id']?.toString() ?? '',
        status: json['execution_status']?.toString() ??
            json['status']?.toString() ??
            'UNKNOWN',
        storeId: json['store_id']?.toString(),
        storeCode: json['store_code']?.toString(),
        storeName: json['store_name']?.toString(),
        executionType: json['execution_type']?.toString(),
        syncMode: json['sync_mode']?.toString(),
        startedAt: _asDate(json['started_at']),
        completedAt: _asDate(json['completed_at']),
        // The history query has used more than one name for the row total
        // across revisions; accept either rather than silently showing zero.
        rowsSynced: _asInt(json['rows_synced'] ?? json['total_rows']),
        tablesSynced: _asInt(json['tables_synced'] ?? json['total_tables']),
        errorMessage: json['error_message']?.toString(),
      );

  String get label => storeName ?? storeCode ?? storeId ?? executionId;

  bool get isFailure {
    final s = status.toUpperCase();
    return s == 'FAILED' || s == 'CANCELLED';
  }

  bool get isSuccess => status.toUpperCase() == 'COMPLETED';

  Duration? get duration => (startedAt == null || completedAt == null)
      ? null
      : completedAt!.difference(startedAt!);
}

/// What `POST /api/sync/control` did.
class SyncControlResult {
  const SyncControlResult({required this.affected, required this.action});

  final int affected;
  final String action;

  factory SyncControlResult.fromJson(Map<String, dynamic> json) =>
      SyncControlResult(
        affected: _asInt(json['affected']),
        action: json['action']?.toString() ?? '',
      );
}

/// The two bulk actions the server accepts. There is deliberately no "resume":
/// `control_stores` only maps PAUSE→PAUSED and STOP→CANCELLED, and a paused
/// execution is resumed by the store agent, not from here.
enum SyncControlAction {
  pause('PAUSE', 'Pause'),
  stop('STOP', 'Stop');

  const SyncControlAction(this.wire, this.label);

  final String wire;
  final String label;
}
