import 'dart:async';
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:nexora_mobile/core/di/capture_providers.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/document_extraction/application/capture_session_controller.dart';
import 'package:nexora_mobile/features/document_extraction/domain/capture_quality.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/capture_frame_overlay.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/capture_page_strip.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/quality_banner.dart';

/// Multi-page document camera.
///
/// The screen owns the platform camera directly rather than through a
/// provider: a `CameraController` is a native resource whose lifetime must
/// track this widget and the app lifecycle exactly, and a provider outliving
/// the screen would hold the camera open behind a locked phone. Everything
/// that is not the camera itself — pages, quality, the queue hand-off — lives
/// in [captureSessionProvider] so it survives rebuilds and stays testable.
class CameraCaptureScreen extends ConsumerStatefulWidget {
  const CameraCaptureScreen({super.key});

  @override
  ConsumerState<CameraCaptureScreen> createState() =>
      _CameraCaptureScreenState();
}

enum _Stage { initialising, ready, permissionDenied, unavailable }

class _CameraCaptureScreenState extends ConsumerState<CameraCaptureScreen>
    with WidgetsBindingObserver {
  final _log = AppLogger.of('CameraCapture');

  CameraController? _controller;
  _Stage _stage = _Stage.initialising;
  String? _failure;
  bool _torch = false;
  bool _shooting = false;
  bool _permanentlyDenied = false;

  /// Verdict banner for the most recent shot.
  CaptureQuality? _review;
  Timer? _reviewTimer;

  /// Where the user last tapped to focus, for the reticle.
  Offset? _focusTap;
  Timer? _focusTimer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // The viewfinder is black on black; a light status bar keeps the clock and
    // battery readable over it.
    SystemChrome.setSystemUIOverlayStyle(SystemUiOverlayStyle.light);
    unawaited(_start());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _reviewTimer?.cancel();
    _focusTimer?.cancel();
    unawaited(_controller?.dispose());
    SystemChrome.setSystemUIOverlayStyle(AppTheme.systemOverlay);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) return;

    // Android reclaims the camera when the app backgrounds; holding a stale
    // controller means a black preview on return with no error to explain it.
    if (state == AppLifecycleState.inactive) {
      setState(() {
        _controller = null;
        _stage = _Stage.initialising;
      });
      unawaited(controller.dispose());
    } else if (state == AppLifecycleState.resumed) {
      unawaited(_start());
    }
  }

  // --- Camera lifecycle ------------------------------------------------------

  Future<void> _start() async {
    if (!mounted) return;
    setState(() {
      _stage = _Stage.initialising;
      _failure = null;
    });

    try {
      final status = await Permission.camera.request();
      if (!mounted) return;
      if (!status.isGranted) {
        setState(() {
          _stage = _Stage.permissionDenied;
          // Only `openAppSettings` can recover a permanent denial — asking
          // again is a no-op the user experiences as a dead button.
          _permanentlyDenied =
              status.isPermanentlyDenied || status.isRestricted;
        });
        return;
      }

      final cameras = await availableCameras();
      if (!mounted) return;
      if (cameras.isEmpty) {
        setState(() => _stage = _Stage.unavailable);
        return;
      }

      final back = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );
      final controller = await _initialise(back);
      if (!mounted) {
        await controller.dispose();
        return;
      }
      setState(() {
        _controller = controller;
        _stage = _Stage.ready;
        _torch = false;
      });
    } on CameraException catch (e) {
      _log.warning('Camera unavailable: ${e.code} ${e.description}');
      if (!mounted) return;
      setState(() {
        _stage = _Stage.unavailable;
        _failure = e.description;
      });
    } on Object catch (e) {
      // Anything else the platform layer can throw — a missing plugin, a
      // vendor camera HAL raising a bare PlatformException — lands the user on
      // the "import from photos" fallback rather than a red screen in the
      // middle of a stockroom.
      _log.warning('Camera could not be opened: $e');
      if (!mounted) return;
      setState(() => _stage = _Stage.unavailable);
    }
  }

  /// Opens the camera at the highest resolution the device will give us,
  /// stepping down if it refuses.
  ///
  /// Resolution is the cheapest OCR accuracy there is: 8pt line-item text on a
  /// 1080p frame is a handful of pixels tall and extracts as noise. Not every
  /// device supports `ultraHigh` for stills, though, so a refusal falls back
  /// rather than leaving the user with no camera at all.
  Future<CameraController> _initialise(CameraDescription camera) async {
    for (final preset in [
      ResolutionPreset.ultraHigh,
      ResolutionPreset.veryHigh,
      ResolutionPreset.high,
    ]) {
      final controller = CameraController(
        camera,
        preset,
        // Video audio would make Android demand RECORD_AUDIO, a permission the
        // app has no business asking for.
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      try {
        await controller.initialize();
        await controller.setFlashMode(FlashMode.off);
        return controller;
      } on CameraException catch (e) {
        await controller.dispose();
        if (preset == ResolutionPreset.high) rethrow;
        _log.info('${preset.name} rejected (${e.code}); stepping down');
      }
    }
    throw CameraException('no_preset', 'No usable capture resolution.');
  }

  Future<void> _toggleTorch() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) return;
    final next = !_torch;
    try {
      await controller.setFlashMode(next ? FlashMode.torch : FlashMode.off);
      if (mounted) setState(() => _torch = next);
    } on CameraException catch (e) {
      _log.info('Torch unavailable: ${e.description}');
    }
  }

  Future<void> _focusAt(Offset local, Size previewSize) async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) return;
    if (previewSize.isEmpty) return;

    final point = Offset(
      (local.dx / previewSize.width).clamp(0.0, 1.0),
      (local.dy / previewSize.height).clamp(0.0, 1.0),
    );
    try {
      if (controller.value.focusPointSupported) {
        await controller.setFocusPoint(point);
        await controller.setFocusMode(FocusMode.auto);
      }
      // Metering off the page as well as focusing on it is what stops a dark
      // stockroom background from blowing out the invoice.
      if (controller.value.exposurePointSupported) {
        await controller.setExposurePoint(point);
      }
    } on CameraException catch (e) {
      _log.fine('Focus request refused: ${e.description}');
    }

    if (!mounted) return;
    setState(() => _focusTap = local);
    _focusTimer?.cancel();
    _focusTimer = Timer(
      const Duration(milliseconds: 900),
      () {
        if (mounted) setState(() => _focusTap = null);
      },
    );
  }

  // --- Capture ---------------------------------------------------------------

  Future<void> _shoot() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized || _shooting) {
      return;
    }

    setState(() => _shooting = true);
    _dismissReview();
    unawaited(HapticFeedback.mediumImpact());

    try {
      final shot = await controller.takePicture();
      final page = await ref
          .read(captureSessionProvider.notifier)
          .addPage(File(shot.path));

      // The plugin's file is in a temp directory the OS may clear at any time;
      // the processed copy under documents/ is the one that has to survive.
      await _deleteQuietly(shot.path);

      if (!mounted) return;
      if (page != null) _showReview(page.quality);
    } on CameraException catch (e) {
      _log.warning('takePicture failed: ${e.code} ${e.description}');
      if (mounted) {
        setState(
          () => _failure = e.description ??
              'The camera could not take that '
                  'picture. Try again.',
        );
      }
    } finally {
      if (mounted) setState(() => _shooting = false);
    }
  }

  Future<void> _importFromGallery() async {
    try {
      final picked = await ImagePicker().pickMultiImage();
      if (picked.isEmpty || !mounted) return;

      final session = ref.read(captureSessionProvider.notifier);
      CapturedPage? last;
      for (final file in picked) {
        last = await session.addPage(File(file.path));
        if (!mounted) return;
      }
      if (last != null) _showReview(last.quality);
    } on PlatformException catch (e) {
      _log.warning('Gallery import failed: ${e.message}');
      if (mounted) {
        setState(() => _failure = 'Could not open the photo library.');
      }
    }
  }

  void _showReview(CaptureQuality quality) {
    _reviewTimer?.cancel();
    setState(() => _review = quality);

    // A clean page needs only a glance of confirmation; a warning deserves
    // reading time; a rejection stays until the user decides, because
    // dismissing it for them is how a blurred page reaches the server.
    final linger = switch (quality.verdict) {
      QualityVerdict.good => const Duration(milliseconds: 1500),
      QualityVerdict.warn => const Duration(seconds: 6),
      QualityVerdict.reject => Duration.zero,
    };
    if (linger == Duration.zero) return;
    _reviewTimer = Timer(linger, () {
      if (mounted) setState(() => _review = null);
    });
  }

  void _dismissReview() {
    _reviewTimer?.cancel();
    if (_review != null) setState(() => _review = null);
  }

  Future<void> _retakeLast() async {
    final session = ref.read(captureSessionProvider);
    if (session.isEmpty) return;
    _dismissReview();
    await ref
        .read(captureSessionProvider.notifier)
        .removePage(session.pages.length - 1);
  }

  // --- Finishing -------------------------------------------------------------

  Future<void> _submit() async {
    final messenger = ScaffoldMessenger.of(context);
    final router = GoRouter.of(context);
    final pageCount = ref.read(captureSessionProvider).pageCount;

    final batchId = await ref.read(captureSessionProvider.notifier).commit();
    if (!mounted) return;
    if (batchId == null) {
      setState(
        () => _failure =
            ref.read(captureSessionProvider).error ?? 'Could not queue.',
      );
      return;
    }

    // Fire the drain rather than await it: the capture is durable now, and
    // holding the user on a viewfinder while a 3 MB upload crawls over store
    // Wi-Fi is exactly the wait the offline queue exists to remove.
    unawaited(_drainQuietly());

    router.pop();
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          '$pageCount page${pageCount == 1 ? '' : 's'} queued for extraction',
        ),
      ),
    );
  }

  Future<void> _drainQuietly() async {
    try {
      await ref.read(captureUploaderProvider).drain();
    } on Object catch (e) {
      // The queue retries on its own schedule; a failure here is not the
      // user's problem at this moment.
      _log.fine('Opportunistic drain failed: $e');
    }
  }

  /// Leaves the screen, confirming first if there is unsubmitted work.
  Future<void> _close() async {
    if (!await _confirmDiscard()) return;
    if (mounted) context.pop();
  }

  /// Confirms before throwing away work. Returns true when it is safe to leave.
  Future<bool> _confirmDiscard() async {
    if (ref.read(captureSessionProvider).isEmpty) return true;

    final pageCount = ref.read(captureSessionProvider).pageCount;
    final discard = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Discard this document?'),
        content: Text(
          '$pageCount captured page${pageCount == 1 ? '' : 's'} will be '
          'deleted. This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Keep capturing'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: TextButton.styleFrom(foregroundColor: AppColors.danger),
            child: const Text('Discard'),
          ),
        ],
      ),
    );

    if (discard != true) return false;
    await ref.read(captureSessionProvider.notifier).discard();
    return true;
  }

  static Future<void> _deleteQuietly(String path) async {
    try {
      final file = File(path);
      if (await file.exists()) await file.delete();
    } on FileSystemException {
      // The OS will clear its own temp directory eventually.
    }
  }

  // --- Build -----------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(captureSessionProvider);

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        await _close();
      },
      child: Scaffold(
        backgroundColor: Colors.black,
        body: Stack(
          fit: StackFit.expand,
          children: [
            _viewfinder(),
            SafeArea(
              child: Column(
                children: [
                  _topBar(session),
                  const Spacer(),
                  if (_failure != null) _failureBanner(),
                  if (_review != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: QualityBanner(
                        quality: _review!,
                        onRetake: _retakeLast,
                        onDismiss: _dismissReview,
                      ),
                    ),
                  CapturePageStrip(
                    pages: session.pages,
                    onRemove: (index) => ref
                        .read(captureSessionProvider.notifier)
                        .removePage(index),
                  ),
                  _controls(session),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _viewfinder() {
    return switch (_stage) {
      _Stage.ready => _preview(),
      _Stage.initialising => const Center(
          child: CircularProgressIndicator(color: Colors.white24),
        ),
      _Stage.permissionDenied => _permissionView(),
      _Stage.unavailable => _unavailableView(),
    };
  }

  Widget _preview() {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      return const SizedBox.shrink();
    }

    // The preview is letterboxed at the sensor's own aspect ratio rather than
    // cropped to fill the screen: on a document camera, anything the user
    // cannot see is content they will discover is missing only after the
    // supplier has left.
    return Center(
      child: LayoutBuilder(
        builder: (context, constraints) => GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapUp: (details) => _focusAt(
            details.localPosition,
            constraints.biggest,
          ),
          child: Stack(
            alignment: Alignment.center,
            children: [
              CameraPreview(controller),
              Positioned.fill(
                child: CaptureFrameOverlay(highlight: _shooting),
              ),
              if (_focusTap != null)
                Positioned(
                  left: _focusTap!.dx - 22,
                  top: _focusTap!.dy - 22,
                  child: const _FocusReticle(),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _topBar(CaptureSessionState session) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 4, 8, 0),
      child: Row(
        children: [
          IconButton(
            onPressed: _close,
            icon: const Icon(Icons.close_rounded),
            color: Colors.white,
            tooltip: 'Close',
          ),
          Expanded(
            child: Text(
              session.isEmpty
                  ? 'Fill the frame with the invoice'
                  : '${session.pageCount} page'
                      '${session.pageCount == 1 ? '' : 's'} captured',
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: Colors.white,
                shadows: [Shadow(blurRadius: 6, color: Colors.black54)],
              ),
            ),
          ),
          if (_stage == _Stage.ready)
            IconButton(
              onPressed: _toggleTorch,
              icon: Icon(
                _torch
                    ? Icons.flashlight_on_rounded
                    : Icons.flashlight_off_rounded,
              ),
              color: _torch ? AppColors.warningInk : Colors.white,
              tooltip: _torch ? 'Torch on' : 'Torch off',
            )
          else
            const SizedBox(width: 48),
        ],
      ),
    );
  }

  Widget _controls(CaptureSessionState session) {
    final canShoot = _stage == _Stage.ready && !_shooting && !session.busy;

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 20),
      color: Colors.black.withValues(alpha: 0.55),
      child: Row(
        children: [
          Expanded(
            child: Align(
              alignment: Alignment.centerLeft,
              child: IconButton(
                onPressed: session.busy ? null : _importFromGallery,
                icon: const Icon(Icons.photo_library_outlined),
                color: Colors.white,
                iconSize: 26,
                tooltip: 'Import from photos',
              ),
            ),
          ),
          _ShutterButton(
            onPressed: canShoot ? _shoot : null,
            busy: session.busy || _shooting,
          ),
          Expanded(
            child: Align(
              alignment: Alignment.centerRight,
              child: FilledButton(
                onPressed: session.isEmpty || session.busy ? null : _submit,
                // The theme's `Size.fromHeight` minimum is an infinite width;
                // left as-is the button stretches across the whole trailing
                // third of the control bar. See the note in `capture_screen`.
                style: FilledButton.styleFrom(
                  minimumSize: const Size(0, 44),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 18,
                    vertical: 12,
                  ),
                ),
                child: const Text('Done'),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _failureBanner() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 10, 4, 10),
        decoration: BoxDecoration(
          color: AppColors.surfaceRaised.withValues(alpha: 0.96),
          borderRadius: BorderRadius.circular(AppTheme.radiusMd),
          border: Border.all(color: AppColors.danger.withValues(alpha: 0.5)),
        ),
        child: Row(
          children: [
            const Icon(
              Icons.error_outline_rounded,
              size: 18,
              color: AppColors.dangerInk,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                _failure!,
                style: const TextStyle(fontSize: 12.5, color: AppColors.text),
              ),
            ),
            IconButton(
              onPressed: () => setState(() => _failure = null),
              icon: const Icon(Icons.close_rounded, size: 18),
              color: AppColors.textMuted,
              visualDensity: VisualDensity.compact,
            ),
          ],
        ),
      ),
    );
  }

  Widget _permissionView() {
    return _Blocked(
      icon: Icons.no_photography_outlined,
      title: 'Camera access is off',
      message: _permanentlyDenied
          ? 'Axythic needs the camera to photograph invoices. Turn it on in '
              'Settings, then come back.'
          : 'Axythic needs the camera to photograph invoices. Nothing is '
              'uploaded until you press Done.',
      actionLabel: _permanentlyDenied ? 'Open settings' : 'Allow camera',
      onAction: _permanentlyDenied ? openAppSettings : _start,
      secondaryLabel: 'Import from photos instead',
      onSecondary: _importFromGallery,
    );
  }

  Widget _unavailableView() {
    return _Blocked(
      icon: Icons.videocam_off_outlined,
      title: 'No camera available',
      // A camera-less tablet is a supported configuration — `android.hardware
      // .camera` is declared `required="false"` — so this is a normal state,
      // not an error.
      message: _failure ??
          'This device has no usable camera. You can still pick an existing '
              'photo or scan of the invoice.',
      actionLabel: 'Import from photos',
      onAction: _importFromGallery,
      secondaryLabel: 'Try again',
      onSecondary: _start,
    );
  }
}

/// Round shutter with a busy state, sized well past the 48dp tap minimum
/// because it is pressed one-handed while the other hand holds the invoice.
class _ShutterButton extends StatelessWidget {
  const _ShutterButton({required this.onPressed, required this.busy});

  final VoidCallback? onPressed;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    return Semantics(
      button: true,
      label: 'Capture page',
      child: GestureDetector(
        onTap: onPressed,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          width: 72,
          height: 72,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
              color: Colors.white.withValues(alpha: enabled ? 0.9 : 0.35),
              width: 3,
            ),
          ),
          child: Center(
            child: busy
                ? const SizedBox(
                    width: 26,
                    height: 26,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.6,
                      color: Colors.white,
                    ),
                  )
                : AnimatedContainer(
                    duration: const Duration(milliseconds: 150),
                    width: 56,
                    height: 56,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: Colors.white.withValues(alpha: enabled ? 1 : 0.35),
                    ),
                  ),
          ),
        ),
      ),
    );
  }
}

/// Brief reticle confirming a tap-to-focus landed.
class _FocusReticle extends StatelessWidget {
  const _FocusReticle();

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 1.4, end: 1),
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOut,
      builder: (context, scale, child) =>
          Transform.scale(scale: scale, child: child),
      child: Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: AppColors.accent, width: 1.6),
        ),
      ),
    );
  }
}

/// Full-screen explanation shown when the viewfinder cannot run.
class _Blocked extends StatelessWidget {
  const _Blocked({
    required this.icon,
    required this.title,
    required this.message,
    required this.actionLabel,
    required this.onAction,
    this.secondaryLabel,
    this.onSecondary,
  });

  final IconData icon;
  final String title;
  final String message;
  final String actionLabel;
  final VoidCallback onAction;
  final String? secondaryLabel;
  final VoidCallback? onSecondary;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(32, 0, 32, 120),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 40, color: AppColors.textMuted),
            const SizedBox(height: 16),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: AppColors.text,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 13,
                height: 1.4,
                color: AppColors.textSoft,
              ),
            ),
            const SizedBox(height: 20),
            FilledButton(onPressed: onAction, child: Text(actionLabel)),
            if (secondaryLabel != null && onSecondary != null)
              TextButton(onPressed: onSecondary, child: Text(secondaryLabel!)),
          ],
        ),
      ),
    );
  }
}
