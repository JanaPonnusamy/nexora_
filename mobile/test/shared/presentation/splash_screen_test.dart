import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/shared/presentation/splash_screen.dart';

void main() {
  Widget buildSplash() => MaterialApp(
        theme: AppTheme.dark,
        home: const SplashScreen(),
      );

  testWidgets('shows the branded startup state', (tester) async {
    await tester.pumpWidget(buildSplash());

    expect(find.text('Axythic'), findsOneWidget);
    expect(find.text('PHARMACY OPERATIONS, SIMPLIFIED'), findsOneWidget);
    expect(find.text('Preparing your workspace'), findsOneWidget);
    expect(find.text('Secure mobile workspace'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('fits on a compact phone without overflowing', (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(buildSplash());

    expect(tester.takeException(), isNull);
  });
}
