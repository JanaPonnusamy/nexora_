import 'package:nexora_mobile/bootstrap.dart';

/// Application entry point. All wiring lives in [bootstrap]; keeping `main`
/// trivial makes it easy to add flavor-specific entry points later
/// (e.g. `main_staging.dart`) that call bootstrap with different config.
Future<void> main() => bootstrap();
