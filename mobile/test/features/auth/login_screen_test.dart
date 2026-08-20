import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/core/widgets/axythic_brand_mark.dart';
import 'package:nexora_mobile/features/auth/presentation/login_screen.dart';

void main() {
  Widget buildLogin() => ProviderScope(
        child: MaterialApp(
          theme: AppTheme.dark,
          home: const LoginScreen(),
        ),
      );

  testWidgets('uses Axythic branding and hides legacy connection details',
      (tester) async {
    await tester.pumpWidget(buildLogin());

    expect(find.byType(AxythicBrandMark), findsOneWidget);
    expect(find.text('Axythic'), findsOneWidget);
    expect(find.text('Welcome back'), findsOneWidget);
    expect(find.textContaining('Nexora'), findsNothing);
    expect(find.textContaining('122.252.246.181'), findsNothing);
    expect(find.text('N'), findsNothing);
    expect(find.text('DEV'), findsNothing);
  });

  testWidgets('remains usable on a compact phone', (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(buildLogin());

    expect(tester.takeException(), isNull);
    expect(find.text('Sign in'), findsWidgets);
    expect(find.byType(SingleChildScrollView), findsOneWidget);
  });
}
