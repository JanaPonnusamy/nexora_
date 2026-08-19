import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import 'package:nexora_mobile/core/di/capture_providers.dart';
import 'package:nexora_mobile/core/router/app_routes.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/document_extraction/application/capture_session_controller.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_queue_repository.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';

/// Root of the Capture tab — the OCR document pipeline's entry point.
///
/// Deliberately a launcher rather than a dashboard: the job that brings
/// someone to this tab is "photograph the invoice in my hand", so the shutter
/// is one tap from the tab bar and everything else is subordinate to it.
class CaptureScreen extends ConsumerStatefulWidget {
  const CaptureScreen({super.key});

  @override
  ConsumerState<CaptureScreen> createState() => _CaptureScreenState();
}

class _CaptureScreenState extends ConsumerState<CaptureScreen> {
  @override
  void initState() {
    super.initState();
    // A crash between writing a page and queuing the batch orphans its
    // directory; nothing else would ever reclaim that space.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(captureStorageProvider).sweepEmptySessions();
    });
  }

  Future<void> _openCamera() =>
      context.pushNamed<void>(AppRoutes.cameraCapture);

  Future<void> _openQueue() => context.pushNamed<void>(AppRoutes.captureQueue);

  /// Import path for a document already photographed, or one scanned on a
  /// desktop scanner and sent to the phone. Goes through the same processing
  /// and quality gate as a live capture, then straight to the camera screen so
  /// the user can add more pages or submit.
  Future<void> _importFromGallery() async {
    final messenger = ScaffoldMessenger.of(context);
    final List<XFile> picked;
    try {
      picked = await ImagePicker().pickMultiImage();
    } on PlatformException {
      // Usually a denied photo-library permission. The camera is still a way
      // through, so this is a message rather than a dead end.
      messenger.showSnackBar(
        const SnackBar(content: Text('Could not open the photo library.')),
      );
      return;
    }
    if (picked.isEmpty || !mounted) return;

    final session = ref.read(captureSessionProvider.notifier);
    for (final file in picked) {
      await session.addPage(File(file.path));
      if (!mounted) return;
    }
    await _openCamera();
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(captureSessionProvider);
    final queue = ref.watch(captureQueueStreamProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Capture')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
        children: [
          if (!session.isEmpty) ...[
            _ResumeCard(
              pageCount: session.pageCount,
              flaggedCount: session.flaggedCount,
              onResume: _openCamera,
              onDiscard: () =>
                  ref.read(captureSessionProvider.notifier).discard(),
            ),
            const SizedBox(height: 16),
          ],
          _ScanCard(onScan: _openCamera, onImport: _importFromGallery),
          const SizedBox(height: 20),
          SectionHeader(
            title: 'IN THE QUEUE',
            icon: Icons.cloud_upload_outlined,
            trailing: TextButton(
              onPressed: _openQueue,
              style: TextButton.styleFrom(
                minimumSize: const Size(0, 32),
                padding: const EdgeInsets.symmetric(horizontal: 10),
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              child: const Text('View all'),
            ),
          ),
          queue.when(
            loading: () => const InlineLoading(),
            error: (e, _) => EmptyState(
              message: 'Could not read the capture queue.\n$e',
              icon: Icons.error_outline_rounded,
            ),
            data: (jobs) => _QueueSummary(jobs, onTap: _openQueue),
          ),
        ],
      ),
    );
  }
}

/// Hero action. One card, one obvious verb.
class _ScanCard extends StatelessWidget {
  const _ScanCard({required this.onScan, required this.onImport});

  final VoidCallback onScan;
  final VoidCallback onImport;

  @override
  Widget build(BuildContext context) {
    return StatusCard(
      accentColor: AppColors.accent,
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: AppColors.accent.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.document_scanner_rounded,
                  color: AppColors.accent,
                  size: 22,
                ),
              ),
              const SizedBox(width: 12),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Scan a supplier invoice',
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    SizedBox(height: 2),
                    Text(
                      'Works offline — pages queue on the device and upload '
                      'when you reconnect.',
                      style: TextStyle(
                        fontSize: 12,
                        height: 1.35,
                        color: AppColors.textMuted,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: onScan,
              icon: const Icon(Icons.photo_camera_rounded, size: 20),
              label: const Text('Open camera'),
              style: FilledButton.styleFrom(
                minimumSize: const Size.fromHeight(AppTheme.minTapTarget),
              ),
            ),
          ),
          const SizedBox(height: 4),
          Center(
            child: TextButton.icon(
              onPressed: onImport,
              icon: const Icon(Icons.photo_library_outlined, size: 18),
              label: const Text('Import from photos'),
            ),
          ),
        ],
      ),
    );
  }
}

/// Shown when the user backed out of the camera mid-document, so half a
/// captured invoice is never silently stranded.
class _ResumeCard extends StatelessWidget {
  const _ResumeCard({
    required this.pageCount,
    required this.flaggedCount,
    required this.onResume,
    required this.onDiscard,
  });

  final int pageCount;
  final int flaggedCount;
  final VoidCallback onResume;
  final VoidCallback onDiscard;

  @override
  Widget build(BuildContext context) {
    return StatusCard(
      accentColor: AppColors.warning,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Unfinished document — $pageCount page'
                  '${pageCount == 1 ? '' : 's'}',
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              if (flaggedCount > 0)
                StatusBadge(
                  label: '$flaggedCount flagged',
                  color: AppColors.warning,
                  dense: true,
                  icon: Icons.info_rounded,
                ),
            ],
          ),
          const SizedBox(height: 4),
          const Text(
            'These pages are on the device but have not been submitted.',
            style: TextStyle(fontSize: 12, color: AppColors.textMuted),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              FilledButton(
                onPressed: onResume,
                // The app theme gives filled buttons `Size.fromHeight`, which
                // is `Size(double.infinity, 52)`. A Row measures inflexible
                // children with unbounded main-axis constraints, so a themed
                // FilledButton dropped straight into a Row asserts on an
                // infinite width. Any button in a Row needs a real minimum.
                style: FilledButton.styleFrom(
                  minimumSize: const Size(0, 44),
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                ),
                child: const Text('Resume'),
              ),
              const SizedBox(width: 8),
              TextButton(
                onPressed: onDiscard,
                style: TextButton.styleFrom(foregroundColor: AppColors.danger),
                child: const Text('Discard'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Counts by state, so a queued capture visibly went somewhere. Tapping any of
/// it opens the queue, where each document can actually be acted on.
class _QueueSummary extends StatelessWidget {
  const _QueueSummary(this.jobs, {required this.onTap});

  final List<CaptureJob> jobs;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    if (jobs.isEmpty) {
      return const EmptyState(
        message: 'Nothing waiting. Captured documents show up here.',
        icon: Icons.inbox_outlined,
      );
    }

    final waiting =
        jobs.where((j) => j.status == DocumentStatus.pendingUpload).length;
    final processing = jobs.where((j) => j.status.isProcessing).length;
    final ready = jobs.where((j) => j.status.needsReview).length;
    final failed = jobs.where((j) => j.status == DocumentStatus.failed).length;

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: MetricRow(
        tiles: [
          MetricTile(
            label: 'Waiting',
            value: '$waiting',
            icon: Icons.schedule_rounded,
            color: AppColors.textMuted,
          ),
          MetricTile(
            label: 'Processing',
            value: '$processing',
            icon: Icons.autorenew_rounded,
            color: AppColors.info,
          ),
          MetricTile(
            label: 'To review',
            value: '$ready',
            icon: Icons.fact_check_outlined,
            color: AppColors.accent,
          ),
          MetricTile(
            label: 'Failed',
            value: '$failed',
            icon: Icons.error_outline_rounded,
            color: failed > 0 ? AppColors.danger : AppColors.textMuted,
          ),
        ],
      ),
    );
  }
}
