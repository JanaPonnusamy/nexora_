/// Pipeline state machine for a document import.
///
/// Mirrors `doc_import.status` on the server exactly (see
/// docs/Document_Extraction_Workflow.md). The server is the source of truth;
/// this enum only interprets what it reports.
enum DocumentStatus {
  /// Queued on this device, not yet accepted by the server. Local-only — the
  /// server never returns it.
  pendingUpload('PENDING_UPLOAD'),

  uploaded('UPLOADED'),
  ocrRunning('OCR_RUNNING'),
  extracted('EXTRACTED'),
  reviewPending('REVIEW_PENDING'),
  saved('SAVED'),

  /// Written into a workbook. `service.export` sets this on every import in
  /// the batch, so it comes back from the server whether or not the export was
  /// started from this device.
  exported('EXPORTED'),

  failed('FAILED');

  const DocumentStatus(this.wire);

  /// The exact string the API uses.
  final String wire;

  static DocumentStatus fromWire(String? value) {
    if (value == null) return DocumentStatus.uploaded;
    final normalised = value.trim().toUpperCase();
    for (final status in DocumentStatus.values) {
      if (status.wire == normalised) return status;
    }
    // An unrecognised status means the server moved ahead of this build.
    // Treating it as in-flight keeps the client polling rather than showing a
    // wrong terminal state.
    return DocumentStatus.uploaded;
  }

  /// True while the server is still working — the client should keep polling.
  bool get isProcessing => switch (this) {
        DocumentStatus.uploaded ||
        DocumentStatus.ocrRunning ||
        DocumentStatus.extracted =>
          true,
        _ => false,
      };

  /// True once the pipeline has stopped, for any reason.
  bool get isTerminal => switch (this) {
        DocumentStatus.reviewPending ||
        DocumentStatus.saved ||
        DocumentStatus.exported ||
        DocumentStatus.failed =>
          true,
        _ => false,
      };

  bool get needsReview => this == DocumentStatus.reviewPending;

  /// True once the invoice is committed — it can be exported, and re-exported.
  bool get isCommitted =>
      this == DocumentStatus.saved || this == DocumentStatus.exported;

  String get label => switch (this) {
        DocumentStatus.pendingUpload => 'Waiting to upload',
        DocumentStatus.uploaded => 'Uploaded',
        DocumentStatus.ocrRunning => 'Reading document',
        DocumentStatus.extracted => 'Extracting',
        DocumentStatus.reviewPending => 'Ready to review',
        DocumentStatus.saved => 'Saved',
        DocumentStatus.exported => 'Exported',
        DocumentStatus.failed => 'Failed',
      };
}

/// Severity of a validation finding, from `doc_import.validation_status`.
enum ValidationStatus {
  pending('PENDING'),
  passed('PASSED'),
  warning('WARNING'),
  failed('FAILED');

  const ValidationStatus(this.wire);

  final String wire;

  static ValidationStatus fromWire(String? value) {
    final normalised = value?.trim().toUpperCase();
    // The import-level status is PASSED/WARNING/FAILED, but an individual
    // finding's severity is ERROR/WARNING (`ValidationSeverity` in
    // `json_contracts.py`). Both arrive here, so ERROR has to read as the
    // failure it is — falling through to PENDING would hide the one finding
    // that actually blocks a save.
    if (normalised == 'ERROR') return ValidationStatus.failed;
    for (final status in ValidationStatus.values) {
      if (status.wire == normalised) return status;
    }
    return ValidationStatus.pending;
  }

  /// Only FAILED blocks a save (and even then the server allows `force`).
  bool get blocksSave => this == ValidationStatus.failed;

  /// Import-level wording. "Errors" rather than "Failed": the invoice has not
  /// failed, it has problems a person can fix.
  String get label => switch (this) {
        ValidationStatus.pending => 'Not checked',
        ValidationStatus.passed => 'All checks passed',
        ValidationStatus.warning => 'Warnings',
        ValidationStatus.failed => 'Errors',
      };
}
