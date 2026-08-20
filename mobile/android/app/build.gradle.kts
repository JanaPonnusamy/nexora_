import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Release signing material, from either of two sources so the same build works
// on a developer machine and in CI:
//
//   android/key.properties   — local, gitignored (storeFile, storePassword,
//                              keyAlias, keyPassword)
//   environment variables    — CI, from repository secrets
//                              (AXYTHIC_KEYSTORE_PATH, AXYTHIC_KEYSTORE_PASSWORD,
//                               AXYTHIC_KEY_ALIAS, AXYTHIC_KEY_PASSWORD)
//
// With neither present the build falls back to debug keys, because otherwise a
// plain `flutter run --release` would stop working for anyone without the
// keystore. That fallback is fine for a local smoke test and catastrophic for a
// store upload, so pass `-PrequireReleaseSigning=true` on any build that
// produces a distributable artifact and the build fails instead of quietly
// shipping a debug-signed binary. Debug-signed uploads are rejected by Play, and
// an app once published under a debug key can never be re-signed with the real
// one — Play matches the signing identity, not the package name.
val keystoreProperties = Properties().apply {
    val file = rootProject.file("key.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}

fun signingValue(propertyKey: String, envKey: String): String? =
    keystoreProperties.getProperty(propertyKey)?.takeIf { it.isNotBlank() }
        ?: System.getenv(envKey)?.takeIf { it.isNotBlank() }

val keystorePath = signingValue("storeFile", "AXYTHIC_KEYSTORE_PATH")
val keystorePassword = signingValue("storePassword", "AXYTHIC_KEYSTORE_PASSWORD")
val keystoreAlias = signingValue("keyAlias", "AXYTHIC_KEY_ALIAS")
val keystoreAliasPassword = signingValue("keyPassword", "AXYTHIC_KEY_PASSWORD")

val hasReleaseSigning =
    keystorePath != null &&
        keystorePassword != null &&
        keystoreAlias != null &&
        keystoreAliasPassword != null &&
        rootProject.file(keystorePath).exists()

// Either source works. The environment variable is what CI uses: `flutter build`
// does not forward `-P` properties to Gradle, so a property alone would be
// unreachable from the command the workflow actually runs.
val requireReleaseSigning =
    (project.findProperty("requireReleaseSigning") as String?)?.toBoolean()
        ?: System.getenv("AXYTHIC_REQUIRE_RELEASE_SIGNING")?.toBoolean()
        ?: false

if (requireReleaseSigning && !hasReleaseSigning) {
    throw GradleException(
        "Release signing was required but no keystore is configured. Provide " +
            "android/key.properties or the AXYTHIC_KEYSTORE_* environment " +
            "variables. See android/key.properties.example."
    )
}

android {
    namespace = "com.nexora.nexora_mobile"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // Store identity for Google Play. Distinct from `namespace` above, which
        // is the Kotlin/R-class package and is deliberately left unchanged —
        // renaming it would mean relocating MainActivity for no user-visible gain.
        applicationId = "com.axythic.mobile"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (hasReleaseSigning) {
            create("release") {
                storeFile = rootProject.file(keystorePath!!)
                storePassword = keystorePassword
                keyAlias = keystoreAlias
                keyPassword = keystoreAliasPassword
            }
        }
    }

    buildTypes {
        release {
            // Phase 6 release hardening. R8 removes unreachable JVM/plugin
            // code and resource shrinking drops Android resources that no
            // release code references. Flutter's Dart AOT tree-shaking still
            // runs separately as part of `flutter build`.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            signingConfig = if (hasReleaseSigning) {
                signingConfigs.getByName("release")
            } else {
                logger.warn(
                    "WARNING: no release keystore configured — signing with debug " +
                        "keys. This artifact cannot be uploaded to Play."
                )
                signingConfigs.getByName("debug")
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
