import 'package:drift/drift.dart';

/// Fallback for platforms that provide neither `dart:io` nor web interop.
QueryExecutor openConnection() {
  throw UnsupportedError(
    'No database implementation is available on this platform.',
  );
}
