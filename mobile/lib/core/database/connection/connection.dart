import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/connection/unsupported.dart'
    if (dart.library.io) 'package:nexora_mobile/core/database/connection/native.dart'
    if (dart.library.js_interop) 'package:nexora_mobile/core/database/connection/web.dart';

/// Opens the platform-appropriate database executor.
///
/// The conditional import above compiles ONLY the implementation for the
/// current platform, so web builds never pull in `dart:ffi` (native) and native
/// builds never pull in the WASM stack.
QueryExecutor openDatabaseConnection() => openConnection();
