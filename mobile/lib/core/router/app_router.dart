import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:nexora_mobile/core/router/app_routes.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/auth/application/auth_state.dart';
import 'package:nexora_mobile/features/auth/presentation/login_screen.dart';
import 'package:nexora_mobile/features/dashboard/presentation/dashboard_screen.dart';
import 'package:nexora_mobile/features/store_selection/presentation/store_selection_screen.dart';
import 'package:nexora_mobile/shared/presentation/splash_screen.dart';

/// Bridges Riverpod's [AuthState] into a [Listenable] GoRouter can refresh on,
/// and centralises the redirect (guard) logic for the whole app.
class RouterNotifier extends ChangeNotifier {
  RouterNotifier(this._ref) {
    _ref.listen<AuthState>(
      authControllerProvider,
      (_, __) => notifyListeners(),
    );
  }

  final Ref _ref;

  String? redirect(BuildContext context, GoRouterState state) {
    final auth = _ref.read(authControllerProvider);
    final location = state.matchedLocation;

    // 1) Still resolving a stored session → hold on the splash screen.
    if (auth.status == AuthStatus.unknown) {
      return location == AppRoutes.splashPath ? null : AppRoutes.splashPath;
    }

    final loggingIn = location == AppRoutes.loginPath;
    final onSplash = location == AppRoutes.splashPath;

    // 2) Not authenticated → force login.
    if (auth.status == AuthStatus.unauthenticated) {
      return loggingIn ? null : AppRoutes.loginPath;
    }

    // 3) Authenticated but no store chosen → store selection.
    if (!auth.hasStore) {
      return location == AppRoutes.storeSelectionPath
          ? null
          : AppRoutes.storeSelectionPath;
    }

    // 4) Fully ready → keep out of the auth/splash funnel.
    if (loggingIn || onSplash || location == AppRoutes.storeSelectionPath) {
      return AppRoutes.dashboardPath;
    }
    return null;
  }
}

final routerNotifierProvider = ChangeNotifierProvider<RouterNotifier>(
  RouterNotifier.new,
);

final routerProvider = Provider<GoRouter>((ref) {
  final notifier = ref.watch(routerNotifierProvider);
  return GoRouter(
    initialLocation: AppRoutes.splashPath,
    refreshListenable: notifier,
    redirect: notifier.redirect,
    routes: [
      GoRoute(
        path: AppRoutes.splashPath,
        name: AppRoutes.splash,
        builder: (_, __) => const SplashScreen(),
      ),
      GoRoute(
        path: AppRoutes.loginPath,
        name: AppRoutes.login,
        builder: (_, __) => const LoginScreen(),
      ),
      GoRoute(
        path: AppRoutes.storeSelectionPath,
        name: AppRoutes.storeSelection,
        builder: (_, __) => const StoreSelectionScreen(),
      ),
      GoRoute(
        path: AppRoutes.dashboardPath,
        name: AppRoutes.dashboard,
        builder: (_, __) => const DashboardScreen(),
      ),
    ],
  );
});
