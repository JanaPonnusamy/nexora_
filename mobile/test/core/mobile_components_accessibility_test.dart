import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';

Widget _app(Widget child) => MaterialApp(
      theme: AppTheme.dark,
      home: Scaffold(body: Center(child: child)),
    );

void main() {
  testWidgets('status badges announce their meaning, not their decoration',
      (tester) async {
    final semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      _app(const StatusBadge(label: 'Waiting', color: AppColors.warning)),
    );

    expect(
      tester.getSemantics(find.byType(StatusBadge)),
      matchesSemantics(label: 'Status: Waiting'),
    );
    semantics.dispose();
  });

  testWidgets('metric tiles announce label and value together', (tester) async {
    final semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      _app(const MetricTile(
        label: 'Pending',
        value: '12',
        icon: Icons.schedule,
        color: AppColors.warning,
      )),
    );

    expect(
      tester.getSemantics(find.byType(MetricTile)),
      matchesSemantics(label: 'Pending: 12'),
    );
    semantics.dispose();
  });

  testWidgets('action tiles expose one labelled button and a useful hint',
      (tester) async {
    final semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      _app(ActionTile(
        title: 'Purchase Workspace',
        subtitle: 'Review products and set quantities',
        icon: Icons.shopping_cart_outlined,
        onTap: () {},
      )),
    );

    expect(
      tester.getSemantics(find.byType(ActionTile)),
      matchesSemantics(
        label: 'Purchase Workspace',
        hint: 'Review products and set quantities',
        isButton: true,
        hasEnabledState: true,
        isEnabled: true,
      ),
    );
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
    await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
    semantics.dispose();
  });
}
