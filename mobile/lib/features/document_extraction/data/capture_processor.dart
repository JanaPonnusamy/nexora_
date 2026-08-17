import 'package:flutter/foundation.dart';
import 'package:image/image.dart' as img;

import 'package:nexora_mobile/features/document_extraction/domain/capture_quality.dart';

/// Decodes a freshly captured page once and derives everything the app needs
/// from that single pass: the upload-ready JPEG and the quality verdict.
///
/// One pass is the whole point. Decoding a 12-megapixel photo in Dart costs
/// roughly a second on a mid-range Android; doing it twice — once to measure,
/// once to shrink — would put a two-second stall between the shutter and the
/// next shot, which is exactly when the user is trying to work quickly.
///
/// The work runs in an isolate ([compute]): the same decode on the UI isolate
/// drops every frame of the shutter animation.
class CaptureProcessor {
  const CaptureProcessor();

  /// Longest edge kept for upload.
  ///
  /// 2400px across A4's long edge is ~200 DPI, the floor PaddleOCR needs to
  /// resolve 8pt line-item text. Phone originals are 4-8 MB; re-encoding at
  /// this size lands around 500-900 KB, which is the difference between an
  /// upload completing and timing out on a store's connection.
  static const int maxUploadEdge = 2400;

  /// Re-encode quality. Below ~80, JPEG ringing around thin glyph strokes
  /// starts costing OCR accuracy.
  static const int jpegQuality = 85;

  /// Processes raw image bytes into an upload-ready page.
  ///
  /// Returns null if the bytes are not a decodable image — HEIC, a truncated
  /// write, or a file the picker handed over that is not really a photo.
  Future<ProcessedCapture?> process(Uint8List bytes) {
    return compute(
      _processCapture,
      _ProcessRequest(
        bytes: bytes,
        maxEdge: maxUploadEdge,
        quality: jpegQuality,
      ),
      debugLabel: 'capture-process',
    );
  }

  /// The same work as [process], on the calling isolate.
  ///
  /// Test-only. Production must go through [process]: the decode is long
  /// enough to be visible as dropped frames if it runs on the UI isolate.
  @visibleForTesting
  static ProcessedCapture? processSync(
    Uint8List bytes, {
    int maxEdge = maxUploadEdge,
    int quality = jpegQuality,
  }) =>
      _processCapture(
        _ProcessRequest(bytes: bytes, maxEdge: maxEdge, quality: quality),
      );
}

/// The result of one processing pass.
class ProcessedCapture {
  const ProcessedCapture({
    required this.jpegBytes,
    required this.quality,
    required this.width,
    required this.height,
  });

  /// Downscaled, orientation-baked JPEG to write to disk and upload.
  final Uint8List jpegBytes;

  final CaptureQuality quality;

  /// Dimensions of [jpegBytes], after downscaling.
  final int width;
  final int height;

  int get byteSize => jpegBytes.length;
}

class _ProcessRequest {
  const _ProcessRequest({
    required this.bytes,
    required this.maxEdge,
    required this.quality,
  });

  final Uint8List bytes;
  final int maxEdge;
  final int quality;
}

// -----------------------------------------------------------------------------
// Isolate body. Everything below runs off the UI isolate and must stay
// top-level (a closure would capture unsendable state).
// -----------------------------------------------------------------------------

ProcessedCapture? _processCapture(_ProcessRequest req) {
  final decoded = img.decodeImage(req.bytes);
  if (decoded == null) return null;

  // EXIF orientation must be baked into the pixels before anything else. The
  // camera plugin on Android commonly writes a landscape buffer with a
  // rotation tag; the server's preprocessor reads pixels, not tags, and would
  // otherwise run OCR on a sideways invoice.
  final upright = img.bakeOrientation(decoded);

  final quality = _analyse(upright);

  final longEdge =
      upright.width > upright.height ? upright.width : upright.height;
  final scaled = longEdge > req.maxEdge
      ? img.copyResize(
          upright,
          width: upright.width >= upright.height ? req.maxEdge : null,
          height: upright.height > upright.width ? req.maxEdge : null,
          interpolation: img.Interpolation.cubic,
        )
      : upright;

  return ProcessedCapture(
    jpegBytes: img.encodeJpg(scaled, quality: req.quality),
    quality: quality,
    width: scaled.width,
    height: scaled.height,
  );
}

/// Long edge of the raster the metrics are computed on.
///
/// Measuring on a fixed small raster is what makes the thresholds below mean
/// anything: variance of the Laplacian scales with resolution, so metrics from
/// a 12MP phone and an 8MP tablet would otherwise be incomparable.
const int _analysisEdge = 720;

/// Share of the frame the metrics look at, centred.
///
/// The capture overlay asks the user to fill this region with the page, so
/// cropping to it keeps a dark, busy stockroom background from being scored as
/// either "sharp detail" or "too dark".
const double _analysisCrop = 0.8;

// Thresholds. These are heuristics calibrated against phone photographs of
// printed invoices, not physical constants — expect to re-tune them once real
// store captures exist. They are deliberately lenient: a false "retake" on a
// good page trains users to ignore the gate entirely.
const double _sharpnessReject = 40;
const double _sharpnessWarn = 100;
const double _glareReject = 0.05;
const double _glareWarn = 0.015;
const double _darkReject = 45;
const double _darkWarn = 75;
const double _brightWarn = 215;

/// Below this the smallest print on an invoice will not survive OCR.
const int _minUsefulLongEdge = 1200;

CaptureQuality _analyse(img.Image source) {
  final scale = _analysisEdge /
      (source.width > source.height ? source.width : source.height);
  final analysis = scale < 1
      ? img.copyResize(
          source,
          width: (source.width * scale).round(),
          height: (source.height * scale).round(),
          interpolation: img.Interpolation.average,
        )
      : source;

  final luma = _lumaPlane(analysis);
  final crop =
      _centreCrop(luma, analysis.width, analysis.height, _analysisCrop);

  final sharpness = _laplacianVariance(crop);
  final glareRatio = _clippedFraction(crop);
  final brightness = _mean(crop.pixels);

  final findings = <QualityFinding>[];

  if (sharpness < _sharpnessReject) {
    findings.add(
      const QualityFinding(QualityIssue.blurred, QualityVerdict.reject),
    );
  } else if (sharpness < _sharpnessWarn) {
    findings.add(
      const QualityFinding(QualityIssue.blurred, QualityVerdict.warn),
    );
  }

  if (glareRatio > _glareReject) {
    findings.add(
      const QualityFinding(QualityIssue.glare, QualityVerdict.reject),
    );
  } else if (glareRatio > _glareWarn) {
    findings.add(const QualityFinding(QualityIssue.glare, QualityVerdict.warn));
  }

  if (brightness < _darkReject) {
    findings.add(
      const QualityFinding(QualityIssue.tooDark, QualityVerdict.reject),
    );
  } else if (brightness < _darkWarn) {
    findings.add(
      const QualityFinding(QualityIssue.tooDark, QualityVerdict.warn),
    );
  } else if (brightness > _brightWarn) {
    findings.add(
      const QualityFinding(QualityIssue.tooBright, QualityVerdict.warn),
    );
  }

  final longEdge = source.width > source.height ? source.width : source.height;
  if (longEdge < _minUsefulLongEdge) {
    findings.add(
      const QualityFinding(QualityIssue.lowResolution, QualityVerdict.warn),
    );
  }

  return CaptureQuality(
    sharpness: sharpness,
    glareRatio: glareRatio,
    brightness: brightness,
    sourceWidth: source.width,
    sourceHeight: source.height,
    findings: findings,
  );
}

/// A single-channel luma view. Pulling the pixels out once and working on a
/// flat [Float64List] avoids the per-pixel `getPixel` object allocation that
/// dominates runtime in the `image` package.
_Plane _lumaPlane(img.Image image) {
  final out = Float64List(image.width * image.height);
  var i = 0;
  for (var y = 0; y < image.height; y++) {
    for (var x = 0; x < image.width; x++) {
      final p = image.getPixel(x, y);
      // Rec. 601 luma — the standard weighting for perceived brightness.
      out[i++] = 0.299 * p.r + 0.587 * p.g + 0.114 * p.b;
    }
  }
  return _Plane(out, image.width, image.height);
}

_Plane _centreCrop(_Plane plane, int width, int height, double fraction) {
  final cw = (width * fraction).round();
  final ch = (height * fraction).round();
  if (cw < 3 || ch < 3) return plane;

  final x0 = (width - cw) ~/ 2;
  final y0 = (height - ch) ~/ 2;
  final out = Float64List(cw * ch);
  for (var y = 0; y < ch; y++) {
    final src = (y0 + y) * width + x0;
    out.setRange(y * cw, y * cw + cw, plane.pixels, src);
  }
  return _Plane(out, cw, ch);
}

/// Variance of the 4-neighbour Laplacian — the standard blur metric.
///
/// The Laplacian responds to intensity changes, so a sharp page of text
/// produces a wide spread of responses and a blurred one collapses toward
/// zero. Variance, not mean, is what separates them: blur suppresses the
/// spread while leaving the average near zero either way.
double _laplacianVariance(_Plane plane) {
  final w = plane.width;
  final h = plane.height;
  if (w < 3 || h < 3) return 0;

  final px = plane.pixels;
  var sum = 0.0;
  var sumSq = 0.0;
  var count = 0;

  for (var y = 1; y < h - 1; y++) {
    final row = y * w;
    for (var x = 1; x < w - 1; x++) {
      final i = row + x;
      final value = px[i - 1] + px[i + 1] + px[i - w] + px[i + w] - 4 * px[i];
      sum += value;
      sumSq += value * value;
      count++;
    }
  }

  if (count == 0) return 0;
  final mean = sum / count;
  return (sumSq / count) - (mean * mean);
}

/// Fraction of pixels clipped to (near) pure white.
///
/// The threshold sits at 250 rather than 255 because a correctly exposed white
/// page peaks in the 230s; only a specular highlight actually clips. Counting
/// from 240 would flag every well-lit invoice.
double _clippedFraction(_Plane plane) {
  var clipped = 0;
  for (final value in plane.pixels) {
    if (value >= 250) clipped++;
  }
  return plane.pixels.isEmpty ? 0 : clipped / plane.pixels.length;
}

double _mean(Float64List values) {
  if (values.isEmpty) return 0;
  var sum = 0.0;
  for (final v in values) {
    sum += v;
  }
  return sum / values.length;
}

class _Plane {
  const _Plane(this.pixels, this.width, this.height);

  final Float64List pixels;
  final int width;
  final int height;
}
