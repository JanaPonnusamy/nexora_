import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;

import 'package:nexora_mobile/features/document_extraction/data/capture_processor.dart';
import 'package:nexora_mobile/features/document_extraction/domain/capture_quality.dart';

/// Exercises the on-device quality gate against synthetic "invoices".
///
/// The images are deliberately not pure black on pure white: a real photograph
/// of paper lands around 235, never 255, and calibrating the glare threshold
/// against an unrealistic 255 background is how the gate ends up flagging
/// every well-lit page.
void main() {
  const paper = 235;
  const ink = 25;

  /// A page of ruled "text" — alternating bands at printed-invoice contrast.
  img.Image page({
    int width = 1600,
    int height = 2000,
    int background = paper,
    int foreground = ink,
    int linePeriod = 16,
  }) {
    final image = img.Image(width: width, height: height);
    img.fill(image, color: img.ColorRgb8(background, background, background));
    for (var y = 0; y < height; y += linePeriod) {
      img.fillRect(
        image,
        x1: 0,
        y1: y,
        x2: width - 1,
        y2: (y + linePeriod ~/ 3).clamp(0, height - 1),
        color: img.ColorRgb8(foreground, foreground, foreground),
      );
    }
    return image;
  }

  Uint8List jpeg(img.Image image) =>
      Uint8List.fromList(img.encodeJpg(image, quality: 92));

  CaptureQuality analyse(img.Image image) {
    final result = CaptureProcessor.processSync(jpeg(image));
    expect(result, isNotNull, reason: 'the synthetic page should decode');
    return result!.quality;
  }

  group('verdicts', () {
    test('a sharp, evenly lit page passes clean', () {
      final quality = analyse(page());

      expect(quality.verdict, QualityVerdict.good);
      expect(quality.findings, isEmpty);
      expect(quality.note, isNull);
    });

    test('a blurred page is rejected', () {
      final quality = analyse(img.gaussianBlur(page(), radius: 12));

      expect(quality.verdict, QualityVerdict.reject);
      expect(quality.issues, contains(QualityIssue.blurred));
      expect(quality.primaryIssue, QualityIssue.blurred);
      expect(quality.note, contains('Blurry'));
    });

    test('blur scores strictly lower than the same page in focus', () {
      // The absolute thresholds are heuristics that will be re-tuned against
      // real captures; the ordering is the part that must never invert.
      final sharp = analyse(page()).sharpness;
      final blurred = analyse(img.gaussianBlur(page(), radius: 12)).sharpness;

      expect(blurred, lessThan(sharp));
    });

    test('a specular highlight over the page is flagged as glare', () {
      final glared = page();
      // A blown-out blob across the middle of the frame, as a ceiling light
      // reflects off a glossy invoice.
      img.fillRect(
        glared,
        x1: 400,
        y1: 700,
        x2: 1200,
        y2: 1300,
        color: img.ColorRgb8(255, 255, 255),
      );

      final quality = analyse(glared);

      expect(quality.issues, contains(QualityIssue.glare));
      expect(quality.glareRatio, greaterThan(0.05));
    });

    test('an underexposed page is flagged as too dark', () {
      final quality = analyse(page(background: 40, foreground: 5));

      expect(quality.issues, contains(QualityIssue.tooDark));
      expect(quality.brightness, lessThan(45));
    });

    test('a page too small for small print is flagged', () {
      final quality = analyse(page(width: 600, height: 800, linePeriod: 8));

      expect(quality.issues, contains(QualityIssue.lowResolution));
      // Low resolution is advice, not a rejection — a small scan still OCRs.
      expect(quality.verdict, QualityVerdict.warn);
    });

    test('a clean page carries no glare from the paper itself', () {
      // Regression guard on the 250 threshold: paper at 235 must not read as
      // clipped, or every correctly exposed invoice gets a glare warning.
      expect(analyse(page()).glareRatio, lessThan(0.001));
    });
  });

  group('output', () {
    test('downscales to the upload ceiling and re-encodes', () {
      final result = CaptureProcessor.processSync(
        jpeg(page(width: 3000, height: 4000)),
      );

      expect(result, isNotNull);
      final longEdge =
          result!.width > result.height ? result.width : result.height;
      expect(longEdge, CaptureProcessor.maxUploadEdge);
      // Aspect ratio is preserved, so the server's deskew sees the real page.
      expect(result.width / result.height, closeTo(3 / 4, 0.01));
      expect(img.decodeJpg(result.jpegBytes), isNotNull);
    });

    test('leaves an already-small page at its original size', () {
      final result = CaptureProcessor.processSync(
        jpeg(page(width: 1200, height: 1600)),
      );

      expect(result!.width, 1200);
      expect(result.height, 1600);
    });

    test('reports the source dimensions it measured, not the resized ones', () {
      final result = CaptureProcessor.processSync(
        jpeg(page(width: 3000, height: 4000)),
      );

      expect(result!.quality.sourceWidth, 3000);
      expect(result.quality.sourceHeight, 4000);
    });

    test('returns null for bytes that are not an image', () {
      final garbage = Uint8List.fromList(List.filled(512, 7));
      expect(CaptureProcessor.processSync(garbage), isNull);
    });
  });

  group('note', () {
    test('names every issue so the queue can explain a flagged page', () {
      const quality = CaptureQuality(
        sharpness: 10,
        glareRatio: 0.2,
        brightness: 100,
        sourceWidth: 100,
        sourceHeight: 100,
        findings: [
          QualityFinding(QualityIssue.blurred, QualityVerdict.reject),
          QualityFinding(QualityIssue.glare, QualityVerdict.warn),
        ],
      );

      expect(quality.verdict, QualityVerdict.reject);
      expect(quality.note, 'reject: Blurry, Glare');
      // The worst finding leads, not the first one listed.
      expect(quality.primaryIssue, QualityIssue.blurred);
    });
  });
}
