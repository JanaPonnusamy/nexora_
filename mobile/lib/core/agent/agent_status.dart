/// Lifecycle of the Legacy Store Agent runtime on this device.
enum AgentStatus {
  /// Constructing; nothing initialised yet.
  initializing,

  /// Establishing the local device identity / registration.
  registering,

  /// Downloading the store configuration from the backend.
  downloadingConfig,

  /// Fully initialised, backend reachable and configuration current.
  ready,

  /// Running on cached configuration; backend is currently unreachable.
  degraded,

  /// No network at all.
  offline,

  /// Initialisation failed in a way that needs attention.
  error,
}

extension AgentStatusX on AgentStatus {
  String get label => switch (this) {
        AgentStatus.initializing => 'Initializing',
        AgentStatus.registering => 'Registering device',
        AgentStatus.downloadingConfig => 'Downloading configuration',
        AgentStatus.ready => 'Ready',
        AgentStatus.degraded => 'Degraded (using cache)',
        AgentStatus.offline => 'Offline',
        AgentStatus.error => 'Error',
      };

  bool get isOperational =>
      this == AgentStatus.ready || this == AgentStatus.degraded;
}
