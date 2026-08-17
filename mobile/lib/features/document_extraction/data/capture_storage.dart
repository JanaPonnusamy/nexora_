import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// Where captured page images live on the device.
///
/// Pages are written under the app's documents directory rather than a cache
/// directory on purpose: the OS is free to evict caches under storage
/// pressure, and losing a photographed invoice that has not uploaded yet is
/// the one failure the whole capture queue exists to prevent.
class CaptureStorage {
  CaptureStorage({Directory? root}) : _root = root;

  static const String _folder = 'captures';

  Directory? _root;

  Future<Directory> _base() async {
    final root = _root ??= await getApplicationDocumentsDirectory();
    final dir = Directory(p.join(root.path, _folder));
    if (!await dir.exists()) await dir.create(recursive: true);
    return dir;
  }

  /// Writes one page of an in-progress capture session.
  ///
  /// Sessions get their own directory so an abandoned capture can be discarded
  /// wholesale, and the page number is part of the filename so the upload
  /// order stays obvious when inspecting the device.
  Future<File> writePage({
    required String sessionId,
    required int pageNumber,
    required Uint8List bytes,
  }) async {
    final base = await _base();
    final dir = Directory(p.join(base.path, sessionId));
    if (!await dir.exists()) await dir.create(recursive: true);

    // The timestamp suffix keeps a retake from colliding with the page it
    // replaces while the old file is still being read by a thumbnail.
    final name = 'page_${pageNumber.toString().padLeft(2, '0')}_'
        '${DateTime.now().millisecondsSinceEpoch}.jpg';
    final file = File(p.join(dir.path, name));
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  /// Deletes a single page image, tolerating one that is already gone.
  Future<void> deletePage(String path) async {
    try {
      final file = File(path);
      if (await file.exists()) await file.delete();
    } on FileSystemException {
      // A file the OS already reclaimed is not an error worth surfacing.
    }
  }

  /// Discards an abandoned session directory and everything in it.
  Future<void> discardSession(String sessionId) async {
    try {
      final base = await _base();
      final dir = Directory(p.join(base.path, sessionId));
      if (await dir.exists()) await dir.delete(recursive: true);
    } on FileSystemException {
      // Best effort — [sweepEmptySessions] will get it on the next launch.
    }
  }

  /// Removes session directories that hold no files.
  ///
  /// A crash between "write the page" and "enqueue the batch" leaves an
  /// orphan directory; nothing else would ever clean it up.
  Future<int> sweepEmptySessions() async {
    var removed = 0;
    try {
      final base = await _base();
      await for (final entity in base.list()) {
        if (entity is! Directory) continue;
        final isEmpty = await entity.list().isEmpty;
        if (isEmpty) {
          await entity.delete();
          removed++;
        }
      }
    } on FileSystemException {
      // Housekeeping must never take the app down.
    }
    return removed;
  }
}
