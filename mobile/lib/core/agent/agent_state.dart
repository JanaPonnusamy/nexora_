import 'package:nexora_mobile/core/agent/agent_status.dart';

/// Immutable snapshot of the store agent, surfaced on the Device / Configuration
/// / Agent Settings screens.
class AgentState {
  const AgentState({
    this.status = AgentStatus.initializing,
    this.deviceId,
    this.registered = false,
    this.configLoaded = false,
    this.backendReachable = false,
    this.apiCompatible = false,
    this.backendLatencyMs,
    this.serverApiVersion,
    this.storeId,
    this.storeName,
    this.lastHealthCheckAt,
    this.lastConfigSyncAt,
    this.lastError,
  });

  const AgentState.initial() : this();

  final AgentStatus status;
  final String? deviceId;
  final bool registered;
  final bool configLoaded;
  final bool backendReachable;
  final bool apiCompatible;
  final int? backendLatencyMs;
  final String? serverApiVersion;
  final String? storeId;
  final String? storeName;
  final DateTime? lastHealthCheckAt;
  final DateTime? lastConfigSyncAt;
  final String? lastError;

  AgentState copyWith({
    AgentStatus? status,
    String? deviceId,
    bool? registered,
    bool? configLoaded,
    bool? backendReachable,
    bool? apiCompatible,
    int? backendLatencyMs,
    bool clearLatency = false,
    String? serverApiVersion,
    String? storeId,
    String? storeName,
    DateTime? lastHealthCheckAt,
    DateTime? lastConfigSyncAt,
    String? lastError,
    bool clearError = false,
  }) {
    return AgentState(
      status: status ?? this.status,
      deviceId: deviceId ?? this.deviceId,
      registered: registered ?? this.registered,
      configLoaded: configLoaded ?? this.configLoaded,
      backendReachable: backendReachable ?? this.backendReachable,
      apiCompatible: apiCompatible ?? this.apiCompatible,
      backendLatencyMs:
          clearLatency ? null : (backendLatencyMs ?? this.backendLatencyMs),
      serverApiVersion: serverApiVersion ?? this.serverApiVersion,
      storeId: storeId ?? this.storeId,
      storeName: storeName ?? this.storeName,
      lastHealthCheckAt: lastHealthCheckAt ?? this.lastHealthCheckAt,
      lastConfigSyncAt: lastConfigSyncAt ?? this.lastConfigSyncAt,
      lastError: clearError ? null : (lastError ?? this.lastError),
    );
  }

  @override
  String toString() => 'AgentState(${status.name}, registered=$registered, '
      'configLoaded=$configLoaded, backendReachable=$backendReachable)';
}
