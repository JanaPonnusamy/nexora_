/// On-device quality verdict for a captured page.
///
/// A blurred or glare-washed photograph is the single largest source of bad
/// OCR output, and the cost of catching it is asymmetric: a retake is two
/// seconds at the counter, while a bad page is discovered minutes later on the
/// review screen — by which time the invoice, and often the supplier's rep,
/// has gone. So the gate runs before the page ever enters the upload queue.
///
/// The gate advises; it never blocks. A faded thermal-print invoice can be
/// genuinely unreadable to these heuristics and still be the only copy that
/// exists, so [QualityVerdict.reject] argues for a retake rather than
/// forbidding the capture.
library;

/// What is wrong with a page, in the user's terms.
enum QualityIssue {
  blurred('Blurry', 'Hold steady and let the camera focus before shooting.'),
  glare('Glare', 'Tilt the page or move out from under the light.'),
  tooDark('Too dark', 'Add light or switch the torch on.'),
  tooBright('Washed out', 'Move away from direct light or turn the torch off.'),
  lowResolution('Low detail', 'Move closer so the page fills the frame.');

  const QualityIssue(this.label, this.advice);

  /// Short label for a chip or banner.
  final String label;

  /// What the user should actually do differently.
  final String advice;
}

/// Severity of a page's worst issue.
enum QualityVerdict {
  /// Nothing worth mentioning.
  good,

  /// Usable, but OCR accuracy will suffer. Shown, not forced.
  warn,

  /// A retake is very likely needed.
  reject;

  bool get isGood => this == QualityVerdict.good;
  bool get needsAttention => this != QualityVerdict.good;
}

/// One detected problem and how badly it presents.
class QualityFinding {
  const QualityFinding(this.issue, this.severity);

  final QualityIssue issue;
  final QualityVerdict severity;
}

/// Measurements and verdict for one captured page.
class CaptureQuality {
  const CaptureQuality({
    required this.sharpness,
    required this.glareRatio,
    required this.brightness,
    required this.sourceWidth,
    required this.sourceHeight,
    this.findings = const [],
  });

  /// Variance of the Laplacian over the framed region of the analysis raster.
  /// Higher is sharper; it has no unit and is only comparable against the
  /// thresholds in `ImageQualityAnalyzer`, which assume that raster's size.
  final double sharpness;

  /// Fraction (0..1) of the framed region that is blown out to pure white —
  /// specular reflection off a glossy invoice or a laminated counter.
  final double glareRatio;

  /// Mean luma, 0..255.
  final double brightness;

  final int sourceWidth;
  final int sourceHeight;

  final List<QualityFinding> findings;

  /// A page with no findings at all.
  static const CaptureQuality unknown = CaptureQuality(
    sharpness: 0,
    glareRatio: 0,
    brightness: 0,
    sourceWidth: 0,
    sourceHeight: 0,
  );

  QualityVerdict get verdict {
    if (findings.any((f) => f.severity == QualityVerdict.reject)) {
      return QualityVerdict.reject;
    }
    if (findings.isNotEmpty) return QualityVerdict.warn;
    return QualityVerdict.good;
  }

  List<QualityIssue> get issues =>
      findings.map((f) => f.issue).toList(growable: false);

  /// The problem to lead with when there is only room for one.
  QualityIssue? get primaryIssue {
    if (findings.isEmpty) return null;
    final worst = findings.firstWhere(
      (f) => f.severity == QualityVerdict.reject,
      orElse: () => findings.first,
    );
    return worst.issue;
  }

  String get headline => switch (verdict) {
        QualityVerdict.good => 'Looks good',
        QualityVerdict.warn => '${primaryIssue?.label} — still usable',
        QualityVerdict.reject => '${primaryIssue?.label} — retake recommended',
      };

  /// Compact string persisted on the page row, so the queue and review screens
  /// can explain a flagged page without decoding the image again.
  /// Null when the page is clean — an empty note is the common case and
  /// storing "good" on every row is noise.
  String? get note {
    if (findings.isEmpty) return null;
    final labels = findings.map((f) => f.issue.label).join(', ');
    return '${verdict.name}: $labels';
  }
}
