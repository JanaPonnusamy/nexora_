package com.nexora.nexora_mobile

import io.flutter.embedding.android.FlutterFragmentActivity

/**
 * FlutterFragmentActivity, not FlutterActivity.
 *
 * local_auth shows AndroidX BiometricPrompt, which is a Fragment and therefore
 * needs a FragmentActivity host. Under the plain FlutterActivity the plugin
 * throws "no_fragment_activity" at the moment the user taps Unlock — it builds,
 * analyses and unit-tests clean, and only fails on a real device.
 *
 * The swap is otherwise behaviour-preserving: FlutterFragmentActivity is the
 * embedding's supported alternative host and is what the plugin documents.
 */
class MainActivity : FlutterFragmentActivity()
