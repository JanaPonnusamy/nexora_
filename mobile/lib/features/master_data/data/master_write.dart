import 'package:nexora_mobile/core/sync/conflict_handler.dart';

/// Decides, using the shared [ConflictHandler] (no custom logic), whether an
/// incoming server record should overwrite the local row.
///
/// - When no local row exists → always apply.
/// - Otherwise the handler compares revisions; we apply unless it decides the
///   local copy is strictly newer ([ConflictResolution.takeClient]). This means
///   records with no version metadata (the common case for these endpoints) are
///   treated as server-authoritative, while a locally-newer version is
///   preserved.
bool shouldApplyRemote(
  ConflictHandler handler, {
  required bool localExists,
  int? localVersion,
  DateTime? localUpdatedAt,
  int? remoteVersion,
  DateTime? remoteUpdatedAt,
}) {
  if (!localExists) return true;
  final resolution = handler.resolve(
    Revision(version: localVersion, updatedAt: localUpdatedAt),
    Revision(version: remoteVersion, updatedAt: remoteUpdatedAt),
  );
  return resolution != ConflictResolution.takeClient;
}
