import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexora_mobile/core/widgets/app_button.dart';
import 'package:nexora_mobile/core/widgets/error_view.dart';

/// Widget tests for shared UI primitives. These deliberately avoid platform
/// plugins (secure storage) and generated code so they run under a plain
/// `flutter test` with no emulator and no build_runner pass.
void main() {
  Widget wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

  group('AppButton', () {
    testWidgets('shows label and fires onPressed when idle', (tester) async {
      var tapped = false;
      await tester.pumpWidget(
        wrap(AppButton(label: 'Sign in', onPressed: () => tapped = true)),
      );

      expect(find.text('Sign in'), findsOneWidget);
      await tester.tap(find.byType(AppButton));
      expect(tapped, isTrue);
    });

    testWidgets('hides label, shows spinner and blocks taps when busy',
        (tester) async {
      var tapped = false;
      await tester.pumpWidget(
        wrap(AppButton(
            label: 'Sign in', busy: true, onPressed: () => tapped = true)),
      );

      expect(find.text('Sign in'), findsNothing);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      await tester.tap(find.byType(AppButton));
      expect(tapped, isFalse);
    });
  });

  group('ErrorView', () {
    testWidgets('renders the message and retry action', (tester) async {
      var retried = false;
      await tester.pumpWidget(
        wrap(ErrorView(message: 'Boom', onRetry: () => retried = true)),
      );

      expect(find.text('Boom'), findsOneWidget);
      await tester.tap(find.text('Retry'));
      expect(retried, isTrue);
    });

    testWidgets('hides retry when no callback is given', (tester) async {
      await tester.pumpWidget(wrap(const ErrorView(message: 'No network')));

      expect(find.text('No network'), findsOneWidget);
      expect(find.text('Retry'), findsNothing);
    });
  });
}
