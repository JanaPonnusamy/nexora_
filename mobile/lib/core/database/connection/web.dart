import 'package:drift/drift.dart';
import 'package:drift/wasm.dart';

/// Web database backed by sqlite3 compiled to WASM (no `dart:ffi`).
///
/// Requires `sqlite3.wasm` and `drift_worker.js` to be served from the web
/// root; both are shipped by the `drift`/`sqlite3` packages and copied into
/// `web/` for a real web deployment. Mobile is the primary target — web is a
/// supported build/verification platform.
QueryExecutor openConnection() {
  return LazyDatabase(() async {
    final result = await WasmDatabase.open(
      databaseName: 'nexora',
      sqlite3Uri: Uri.parse('sqlite3.wasm'),
      driftWorkerUri: Uri.parse('drift_worker.js'),
    );
    return result.resolvedExecutor;
  });
}
