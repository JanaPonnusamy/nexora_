import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/document_page_view.dart';

/// The page viewer is the one surface that would fail silently if it fetched
/// by URL: these endpoints are auth-gated, so a bare `Image.network` renders a
/// broken image and never says why. Every fetch here has to go through the
/// provider, which uses the Dio client that carries the bearer token.
void main() {
  const importId = 12;

  DocumentPageKey key(int page, DocumentImageSource source) =>
      (importId: importId, page: page, source: source);

  Widget host(List<Override> overrides, {int pageCount = 1}) => ProviderScope(
        overrides: overrides,
        child: MaterialApp(
          theme: AppTheme.dark,
          home: const DocumentPageViewer(
            importId: importId,
            pageCount: 2,
          ),
        ),
      );

  testWidgets('waits on the authenticated fetch rather than a URL',
      (tester) async {
    final requested = <DocumentPageKey>[];
    await tester.pumpWidget(
      host([
        for (final source in DocumentImageSource.values)
          documentPageImageProvider(key(1, source)).overrideWith((ref) {
            requested.add(key(1, source));
            // Never completes: the point is that the screen waits on the
            // client call instead of handing a path to the image widget.
            return Completer<Uint8List>().future;
          }),
      ]),
    );
    await tester.pump();

    expect(requested, [key(1, DocumentImageSource.preview)]);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.byType(Image), findsNothing);
  });

  testWidgets('a missing page image is explained, not left broken',
      (tester) async {
    await tester.pumpWidget(
      host([
        documentPageImageProvider(key(1, DocumentImageSource.preview))
            .overrideWith(
          (ref) => Future<Uint8List>.error(
            const ApiException(message: 'Preview not found', statusCode: 404),
          ),
        ),
      ]),
    );
    await tester.pumpAndSettle();

    expect(
      find.textContaining('This page image is not on the server'),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('a failure that is not a 404 shows what went wrong',
      (tester) async {
    await tester.pumpWidget(
      host([
        documentPageImageProvider(key(1, DocumentImageSource.preview))
            .overrideWith(
          (ref) => Future<Uint8List>.error(
            const ApiException(message: 'Cannot reach the server.'),
          ),
        ),
      ]),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Cannot reach the server.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('switching to the original asks for the other rendering',
      (tester) async {
    final requested = <DocumentImageSource>[];
    await tester.pumpWidget(
      host([
        for (final source in DocumentImageSource.values)
          documentPageImageProvider(key(1, source)).overrideWith((ref) {
            requested.add(source);
            return Completer<Uint8List>().future;
          }),
      ]),
    );
    await tester.pump();

    // The preprocessed image is the default because it is what OCR read; the
    // original is there for when preprocessing itself is the suspect.
    expect(requested, [DocumentImageSource.preview]);

    await tester.tap(find.text('Original'));
    await tester.pump();

    expect(requested.last, DocumentImageSource.original);
    expect(find.text('Cleaned'), findsOneWidget);
  });

  testWidgets('a multi-page document says which page is on screen',
      (tester) async {
    await tester.pumpWidget(
      host([
        for (var page = 1; page <= 2; page++)
          documentPageImageProvider(key(page, DocumentImageSource.preview))
              .overrideWith((ref) => Completer<Uint8List>().future),
      ]),
    );
    await tester.pump();

    expect(find.text('Page 1 of 2'), findsOneWidget);

    await tester.fling(find.byType(PageView), const Offset(-400, 0), 1000);
    // Explicit pumps, not pumpAndSettle: a page still loading shows an
    // indeterminate spinner, which by design never stops animating.
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(find.text('Page 2 of 2'), findsOneWidget);
  });
}
