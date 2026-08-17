import 'package:nexora_mobile/features/auth/data/models/app_user.dart';

/// A capability is a coarse permission the navigation layer reasons about,
/// resolved from the `modules[]` array in the login / `/api/auth/me` payload.
///
/// This mirrors the web console's approach (`frontend/src/types/access.ts`):
/// backend module codes are matched to capabilities by case-insensitive
/// substring, because the seeded codes are inconsistent
/// (`PROCUREMENT_CYCLE_REFRESH`, `supplier_stock_analysis`, `AUDIT_LOG`, …).
///
/// This gate is **UX only**. The server is the security boundary — and today it
/// does not enforce `can_create`/`can_edit`/`can_delete`/`can_export` at all,
/// so hiding a tab here must never be mistaken for preventing an action.
enum AppCapability {
  /// Always granted; the landing surface.
  home,

  /// OCR document capture and review.
  capture,

  /// Procurement: cycles, workspace, suppliers, distribution.
  procurement,

  /// Sync and store-agent visibility.
  sync,

  /// Settings and diagnostics. Always granted.
  settings;

  /// Module-code fragments that grant this capability, lower-cased.
  ///
  /// Empty means "not gated on any module code" — see [Capabilities.has].
  List<String> get moduleMatches => switch (this) {
        AppCapability.home => const [],
        AppCapability.capture => const ['document', 'extraction', 'invoice'],
        AppCapability.procurement => const [
            'procurement',
            'purchase',
            'supplier',
            'demand',
          ],
        AppCapability.sync => const [],
        AppCapability.settings => const [],
      };
}

/// Resolves which [AppCapability]s the signed-in user holds.
class Capabilities {
  const Capabilities._(this._granted);

  final Set<AppCapability> _granted;

  /// Everything visible. Used before a user resolves and for unrestricted
  /// accounts.
  static const Capabilities all = Capabilities._({
    AppCapability.home,
    AppCapability.capture,
    AppCapability.procurement,
    AppCapability.sync,
    AppCapability.settings,
  });

  /// Derives capabilities from [user].
  ///
  /// Two cases resolve to [all], both deliberately matching the web console so
  /// the same account sees the same modules on both surfaces:
  ///  * platform users, who bypass the module matrix server-side; and
  ///  * users whose `modules[]` is empty, which the backend returns when no
  ///    `role_module_access` rows are seeded — treating that as "deny all"
  ///    would present a working login with an empty app.
  factory Capabilities.forUser(AppUser? user) {
    if (user == null || user.isPlatformUser || user.modules.isEmpty) {
      return all;
    }

    final codes = user.modules
        .where((m) => m.canView)
        .map((m) => m.module.toLowerCase())
        .toList();

    final granted = <AppCapability>{};
    for (final capability in AppCapability.values) {
      final matches = capability.moduleMatches;
      // A capability with no declared matcher is not module-gated.
      if (matches.isEmpty) {
        granted.add(capability);
        continue;
      }
      if (codes.any((code) => matches.any(code.contains))) {
        granted.add(capability);
      }
    }
    return Capabilities._(granted);
  }

  bool has(AppCapability capability) => _granted.contains(capability);
}
