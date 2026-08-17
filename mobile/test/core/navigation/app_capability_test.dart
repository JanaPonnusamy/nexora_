import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/navigation/app_capability.dart';
import 'package:nexora_mobile/features/auth/data/models/app_user.dart';
import 'package:nexora_mobile/features/auth/data/models/module_permission.dart';

AppUser _user({
  bool isPlatformUser = false,
  List<ModulePermission> modules = const [],
}) =>
    AppUser(
      userId: 'u-1',
      username: 'tester',
      isPlatformUser: isPlatformUser,
      modules: modules,
    );

ModulePermission _module(String code, {bool canView = true}) =>
    ModulePermission(module: code, name: code, canView: canView);

void main() {
  group('Capabilities.forUser', () {
    test('a null user sees everything (pre-session default)', () {
      final caps = Capabilities.forUser(null);
      for (final capability in AppCapability.values) {
        expect(caps.has(capability), isTrue, reason: capability.name);
      }
    });

    test('a platform user bypasses the module matrix', () {
      final caps = Capabilities.forUser(
        _user(isPlatformUser: true, modules: [_module('STOCK')]),
      );
      expect(caps.has(AppCapability.procurement), isTrue);
      expect(caps.has(AppCapability.capture), isTrue);
    });

    test('an empty modules list is permissive, not deny-all', () {
      // The backend returns modules: [] when no role_module_access rows are
      // seeded. Treating that as deny-all would present an empty app to a
      // user who logged in successfully.
      final caps = Capabilities.forUser(_user());
      expect(caps.has(AppCapability.procurement), isTrue);
      expect(caps.has(AppCapability.capture), isTrue);
    });

    test('matches module codes by case-insensitive substring', () {
      // The seeded codes are inconsistent, e.g. PROCUREMENT_CYCLE_REFRESH and
      // supplier_stock_analysis, so exact matching would never fire.
      final caps = Capabilities.forUser(
        _user(modules: [_module('PROCUREMENT_CYCLE_REFRESH')]),
      );
      expect(caps.has(AppCapability.procurement), isTrue);

      final lower = Capabilities.forUser(
        _user(modules: [_module('supplier_stock_analysis')]),
      );
      expect(lower.has(AppCapability.procurement), isTrue);
    });

    test('withholds a capability whose module is absent', () {
      final caps = Capabilities.forUser(_user(modules: [_module('REPORTS')]));
      expect(caps.has(AppCapability.procurement), isFalse);
      expect(caps.has(AppCapability.capture), isFalse);
    });

    test('a module the user cannot view does not grant its capability', () {
      final caps = Capabilities.forUser(
        _user(modules: [_module('PROCUREMENT_CYCLE_REFRESH', canView: false)]),
      );
      expect(caps.has(AppCapability.procurement), isFalse);
    });

    test('ungated capabilities survive a restrictive module set', () {
      // Home, Sync and Settings declare no matchers, so a user with an
      // unrelated module set can still reach the shell and sign out.
      final caps = Capabilities.forUser(_user(modules: [_module('REPORTS')]));
      expect(caps.has(AppCapability.home), isTrue);
      expect(caps.has(AppCapability.sync), isTrue);
      expect(caps.has(AppCapability.settings), isTrue);
    });
  });
}
