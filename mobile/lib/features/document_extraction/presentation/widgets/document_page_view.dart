import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/capture_providers.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';

/// Which rendering of a page to fetch.
enum DocumentImageSource {
  /// The preprocessed image — deskewed, cleaned, and the one OCR actually
  /// read. The right default for review: it is what produced the numbers on
  /// screen.
  preview,

  /// The untouched photograph, for when preprocessing itself is suspect.
  original,
}

/// Identifies one page image. A record, so the family key compares by value
/// and two widgets asking for the same page share one fetch.
typedef DocumentPageKey = ({
  int importId,
  int page,
  DocumentImageSource source,
});

/// Page images are auth-gated like every other endpoint, so they are fetched
/// through Dio (which carries the bearer token) rather than by URL.
///
/// A bare `Image.network` on these paths returns 401 and renders as a broken
/// image with no explanation — the web console solves the same problem in
/// `useAuthorizedImage.ts`.
final documentPageImageProvider =
    FutureProvider.autoDispose.family<Uint8List, DocumentPageKey>(
  (ref, key) async {
    final api = ref.watch(documentExtractionApiProvider);
    final path = switch (key.source) {
      DocumentImageSource.preview =>
        api.previewPath(key.importId, page: key.page),
      DocumentImageSource.original =>
        api.originalPath(key.importId, page: key.page),
    };
    return Uint8List.fromList(await api.imageBytes(path));
  },
);

/// Full-screen look at the pages the extraction came from.
///
/// The point of this screen is comparison: a reviewer reads a number on the
/// invoice and checks it against the field the pipeline filled in. So it
/// zooms, it pages, and it can switch to the original when the preprocessed
/// image is the thing in doubt.
class DocumentPageViewer extends ConsumerStatefulWidget {
  const DocumentPageViewer({
    super.key,
    required this.importId,
    required this.pageCount,
    this.initialPage = 1,
  });

  final int importId;
  final int pageCount;
  final int initialPage;

  /// Pushed on the root navigator: a page being read at arm's length should
  /// not have a tab bar across the bottom of it.
  static Future<void> open(
    BuildContext context, {
    required int importId,
    required int pageCount,
    int initialPage = 1,
  }) {
    return Navigator.of(context, rootNavigator: true).push<void>(
      MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => DocumentPageViewer(
          importId: importId,
          pageCount: pageCount,
          initialPage: initialPage,
        ),
      ),
    );
  }

  @override
  ConsumerState<DocumentPageViewer> createState() => _DocumentPageViewerState();
}

class _DocumentPageViewerState extends ConsumerState<DocumentPageViewer> {
  late final PageController _controller;
  late int _page = widget.initialPage.clamp(1, _pages);
  DocumentImageSource _source = DocumentImageSource.preview;

  int get _pages => widget.pageCount < 1 ? 1 : widget.pageCount;

  @override
  void initState() {
    super.initState();
    _controller = PageController(initialPage: _page - 1);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.canvas,
      appBar: AppBar(
        title: Text(
          _pages == 1 ? 'Invoice page' : 'Page $_page of $_pages',
        ),
        actions: [
          TextButton.icon(
            onPressed: () => setState(
              () => _source = _source == DocumentImageSource.preview
                  ? DocumentImageSource.original
                  : DocumentImageSource.preview,
            ),
            icon: const Icon(Icons.compare_rounded, size: 16),
            label: Text(
              _source == DocumentImageSource.preview ? 'Original' : 'Cleaned',
            ),
            style: TextButton.styleFrom(
              minimumSize: const Size(0, 36),
              padding: const EdgeInsets.symmetric(horizontal: 12),
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: PageView.builder(
              controller: _controller,
              itemCount: _pages,
              onPageChanged: (index) => setState(() => _page = index + 1),
              itemBuilder: (context, index) => _Page(
                key: ValueKey('${_source.name}-${index + 1}'),
                importId: widget.importId,
                page: index + 1,
                source: _source,
              ),
            ),
          ),
          if (_pages > 1)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 14),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  for (var i = 1; i <= _pages; i++)
                    Container(
                      width: i == _page ? 20 : 7,
                      height: 7,
                      margin: const EdgeInsets.symmetric(horizontal: 3),
                      decoration: BoxDecoration(
                        color: i == _page
                            ? AppColors.accent
                            : AppColors.ruleStrong,
                        borderRadius: BorderRadius.circular(999),
                      ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _Page extends ConsumerWidget {
  const _Page({
    super.key,
    required this.importId,
    required this.page,
    required this.source,
  });

  final int importId;
  final int page;
  final DocumentImageSource source;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final key = (importId: importId, page: page, source: source);
    final image = ref.watch(documentPageImageProvider(key));

    return image.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (error, _) => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: EmptyState(
            icon: Icons.image_not_supported_outlined,
            message: error is ApiException && error.statusCode == 404
                // A 404 here is ordinary: preprocessing only writes a preview
                // for pages it could handle, and reclaimed exports drop them.
                ? 'This page image is not on the server.\n'
                    'Try the other rendering.'
                : 'Could not load this page.\n'
                    '${error is ApiException ? error.message : error}',
          ),
        ),
      ),
      data: (bytes) => InteractiveViewer(
        maxScale: 6,
        child: Center(
          child: Image.memory(
            bytes,
            fit: BoxFit.contain,
            // Nothing is cropped: a total hidden off-frame is a total the
            // reviewer cannot check.
            errorBuilder: (_, __, ___) => const EmptyState(
              icon: Icons.broken_image_outlined,
              message: 'That page could not be decoded.',
            ),
          ),
        ),
      ),
    );
  }
}
