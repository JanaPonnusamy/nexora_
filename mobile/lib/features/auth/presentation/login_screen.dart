import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/app_button.dart';
import 'package:nexora_mobile/core/widgets/app_text_field.dart';
import 'package:nexora_mobile/core/widgets/axythic_brand_mark.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';

/// Credential entry against `POST /api/auth/login`. On success the router
/// advances to store selection automatically (redirect off AuthState).
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _password = TextEditingController();
  bool _obscure = true;

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_formKey.currentState!.validate()) return;
    await ref.read(authControllerProvider.notifier).login(
          username: _username.text,
          password: _password.text,
        );
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    // Surface auth errors as a snackbar.
    ref.listen(authControllerProvider.select((s) => s.errorMessage),
        (_, message) {
      if (message != null && message.isNotEmpty) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(
            SnackBar(
              content: Text(message),
              backgroundColor: AppColors.danger,
            ),
          );
        ref.read(authControllerProvider.notifier).clearError();
      }
    });

    return Scaffold(
      body: Stack(
        fit: StackFit.expand,
        children: [
          const _LoginBackdrop(),
          SafeArea(
            child: LayoutBuilder(
              builder: (context, constraints) => SingleChildScrollView(
                keyboardDismissBehavior:
                    ScrollViewKeyboardDismissBehavior.onDrag,
                padding: const EdgeInsets.fromLTRB(20, 24, 20, 28),
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    minHeight: constraints.maxHeight - 52,
                  ),
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 440),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          const _Header(),
                          const SizedBox(height: 32),
                          Container(
                            padding: const EdgeInsets.fromLTRB(22, 24, 22, 22),
                            decoration: BoxDecoration(
                              color: AppColors.surface.withValues(alpha: 0.88),
                              borderRadius: BorderRadius.circular(24),
                              border: Border.all(color: AppColors.rule),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withValues(alpha: 0.2),
                                  blurRadius: 32,
                                  offset: const Offset(0, 16),
                                ),
                              ],
                            ),
                            child: AutofillGroup(
                              child: Form(
                                key: _formKey,
                                child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.stretch,
                                  children: [
                                    Text(
                                      'Sign in',
                                      style: Theme.of(context)
                                          .textTheme
                                          .titleLarge
                                          ?.copyWith(
                                            fontWeight: FontWeight.w700,
                                            letterSpacing: -0.3,
                                          ),
                                    ),
                                    const SizedBox(height: 5),
                                    Text(
                                      'Use your workspace credentials to continue.',
                                      style: Theme.of(context)
                                          .textTheme
                                          .bodySmall
                                          ?.copyWith(
                                            color: AppColors.textMuted,
                                            height: 1.4,
                                          ),
                                    ),
                                    const SizedBox(height: 24),
                                    AppTextField(
                                      label: 'Username',
                                      controller: _username,
                                      hintText: 'Enter your username',
                                      keyboardType: TextInputType.text,
                                      textInputAction: TextInputAction.next,
                                      prefixIcon:
                                          const Icon(Icons.person_outline),
                                      autofillHints: const [
                                        AutofillHints.username,
                                      ],
                                      enabled: !auth.busy,
                                      validator: (v) =>
                                          (v == null || v.trim().isEmpty)
                                              ? 'Username is required'
                                              : null,
                                    ),
                                    const SizedBox(height: 18),
                                    AppTextField(
                                      label: 'Password',
                                      controller: _password,
                                      hintText: 'Enter your password',
                                      obscureText: _obscure,
                                      textInputAction: TextInputAction.done,
                                      prefixIcon:
                                          const Icon(Icons.lock_outline),
                                      autofillHints: const [
                                        AutofillHints.password,
                                      ],
                                      enabled: !auth.busy,
                                      onSubmitted: (_) => _submit(),
                                      suffixIcon: IconButton(
                                        tooltip: _obscure
                                            ? 'Show password'
                                            : 'Hide password',
                                        icon: Icon(
                                          _obscure
                                              ? Icons.visibility_outlined
                                              : Icons.visibility_off_outlined,
                                        ),
                                        onPressed: () => setState(
                                          () => _obscure = !_obscure,
                                        ),
                                      ),
                                      validator: (v) => (v == null || v.isEmpty)
                                          ? 'Password is required'
                                          : null,
                                    ),
                                    const SizedBox(height: 26),
                                    AppButton(
                                      label: 'Sign in',
                                      busy: auth.busy,
                                      onPressed: _submit,
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(height: 22),
                          const _SecurityFooter(),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          height: 92,
          width: 92,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: RadialGradient(
              colors: [
                AppColors.accent.withValues(alpha: 0.16),
                AppColors.accent.withValues(alpha: 0),
              ],
            ),
          ),
          alignment: Alignment.center,
          child: const AxythicBrandMark(width: 52, height: 58),
        ),
        const SizedBox(height: 8),
        ShaderMask(
          blendMode: BlendMode.srcIn,
          shaderCallback: (bounds) => const LinearGradient(
            colors: [Color(0xFFEAF6FF), Color(0xFF93B8FD)],
          ).createShader(bounds),
          child: const Text(
            'Axythic',
            style: TextStyle(
              color: Colors.white,
              fontSize: 27,
              height: 1,
              fontWeight: FontWeight.w700,
              letterSpacing: -0.8,
            ),
          ),
        ),
        const SizedBox(height: 20),
        Text(
          'Welcome back',
          style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.w700,
                letterSpacing: -0.5,
              ),
        ),
        const SizedBox(height: 8),
        Text(
          'Your secure pharmacy workspace',
          textAlign: TextAlign.center,
          style: Theme.of(context)
              .textTheme
              .bodyMedium
              ?.copyWith(color: AppColors.textMuted),
        ),
      ],
    );
  }
}

class _SecurityFooter extends StatelessWidget {
  const _SecurityFooter();

  @override
  Widget build(BuildContext context) {
    return const Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(
          Icons.shield_outlined,
          size: 15,
          color: AppColors.textMuted,
        ),
        SizedBox(width: 7),
        Flexible(
          child: Text(
            'Protected access to your workspace',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.textMuted,
              fontSize: 11.5,
              letterSpacing: 0.15,
            ),
          ),
        ),
      ],
    );
  }
}

class _LoginBackdrop extends StatelessWidget {
  const _LoginBackdrop();

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        const DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Color(0xFF0D1623), AppColors.canvas, Color(0xFF080C12)],
              stops: [0, 0.5, 1],
            ),
          ),
        ),
        Positioned(
          top: -180,
          right: -150,
          child: Container(
            width: 360,
            height: 360,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(
                colors: [
                  AppColors.accent.withValues(alpha: 0.13),
                  AppColors.accent.withValues(alpha: 0),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}
