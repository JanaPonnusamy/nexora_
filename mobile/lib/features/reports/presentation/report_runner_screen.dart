import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/reports/application/reports_providers.dart';
import 'package:nexora_mobile/features/reports/domain/report_formatting.dart';
import 'package:nexora_mobile/features/reports/domain/report_models.dart';
import 'package:nexora_mobile/features/reports/presentation/widgets/report_filter_sheet.dart';
import 'package:nexora_mobile/features/reports/presentation/widgets/report_row_card.dart';

/// Runs one report and shows its result.
///
/// The screen is generic: which filters it offers, what columns come back and
/// how each is formatted are all read from the catalog entry and the response.
class ReportRunnerScreen extends ConsumerStatefulWidget {
  const ReportRunnerScreen({super.key, required this.def});

  final ReportDef def;

  @override
  ConsumerState<ReportRunnerScreen> createState() => _ReportRunnerScreenState();
}

class _ReportRunnerScreenState extends ConsumerState<ReportRunnerScreen> {
  final _log = AppLogger.of('ReportRunner');

  late ReportFilters _filters = ReportFilters.defaultsFor(widget.def);
  ReportResult? _result;
  String? _error;
  bool _running = false;

  /// True when the figures on screen came from the local cache because the
  /// server could not be reached. Surfaced rather than tracked silently: a
  /// stale stock figure shown as current is how someone orders against numbers
  /// that moved yesterday.
  bool _fromCache = false;

  /// How many rows to render at once. These reports return up to a few
  /// thousand rows; building every card would drop frames on the first scroll,
  /// and nobody reads past the first screenful without filtering anyway.
  static const int _pageSize = 50;
  int _visible = _pageSize;

  @override
  void initState() {
    super.initState();
    // A report that needs nothing runs on arrival — making someone tap "Run"
    // to see a report they already chose is a step for its own sake.
    if (widget.def.runsImmediately) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _run());
    }
  }

  Future<void> _run() async {
    final scope = ref.read(reportScopeProvider);
    if (scope == null) {
      setState(() => _error = 'No store is selected.');
      return;
    }
    if (!_filters.satisfies(widget.def)) {
      await _editFilters();
      return;
    }

    setState(() {
      _running = true;
      _error = null;
    });
    try {
      final outcome = await ref.read(reportsRepositoryProvider).run(
            def: widget.def,
            tenantId: scope.tenantId,
            storeId: scope.storeId,
            filters: _filters,
          );
      if (!mounted) return;
      setState(() {
        _result = outcome.result;
        _fromCache = outcome.fromCache;
        _visible = _pageSize;
      });
    } on ApiException catch (e) {
      _log.warning('${widget.def.key} failed: ${e.message}');
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  Future<void> _editFilters() async {
    final updated = await showModalBottomSheet<ReportFilters>(
      context: context,
      backgroundColor: AppColors.surfaceRaised,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => ReportFilterSheet(def: widget.def, filters: _filters),
    );
    if (updated == null || !mounted) return;
    setState(() => _filters = updated);
    await _run();
  }

  Future<void> _share() async {
    final result = _result;
    if (result == null || result.isEmpty) return;

    final messenger = ScaffoldMessenger.of(context);
    try {
      // Written to a temp file rather than shared as a text blob: a CSV body
      // pasted into a message is unusable, whereas a file opens in Excel.
      final dir = await getTemporaryDirectory();
      final name = '${widget.def.key}-${DateTime.now().millisecondsSinceEpoch}'
          '.csv';
      final file = File('${dir.path}/$name');
      await file.writeAsString(reportToCsv(result));

      await Share.shareXFiles(
        [XFile(file.path, mimeType: 'text/csv')],
        subject: '${result.title} — ${_filters.summary(widget.def)}',
      );
    } on Object catch (e) {
      _log.warning('Share failed: $e');
      messenger.showSnackBar(
        const SnackBar(content: Text('Could not share the report.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final result = _result;
    final hasRows = result != null && !result.isEmpty;

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.def.label),
        actions: [
          if (hasRows)
            IconButton(
              onPressed: _share,
              icon: const Icon(Icons.ios_share_rounded),
              tooltip: 'Share as CSV',
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _run,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            if (_fromCache && result != null)
              SliverToBoxAdapter(
                child: _StaleBanner(fetchedAt: result.fetchedAt),
              ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                child: _FilterBar(
                  def: widget.def,
                  filters: _filters,
                  result: result,
                  running: _running,
                  onEdit: _editFilters,
                ),
              ),
            ),
            if (_error != null)
              SliverToBoxAdapter(child: _errorCard())
            else if (_running && result == null)
              const SliverFillRemaining(
                hasScrollBody: false,
                child: Center(child: CircularProgressIndicator()),
              )
            else if (result == null)
              SliverFillRemaining(
                hasScrollBody: false,
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(32),
                    child: EmptyState(
                      message: widget.def.runsImmediately
                          ? 'Pull down to run this report.'
                          : 'Set the filters above, then run the report.',
                      icon: Icons.tune_rounded,
                    ),
                  ),
                ),
              )
            else if (result.isEmpty)
              const SliverFillRemaining(
                hasScrollBody: false,
                child: Center(
                  child: Padding(
                    padding: EdgeInsets.all(32),
                    child: EmptyState(
                      message: 'No rows matched these filters.',
                      icon: Icons.filter_alt_off_outlined,
                    ),
                  ),
                ),
              )
            else ...[
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: ReportSummaryCard(result: result),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
                sliver: SliverList.builder(
                  itemCount: _itemCount(result),
                  itemBuilder: (context, index) {
                    if (index >= _visible) return _moreButton(result);
                    return ReportRowCard(
                      row: result.rows[index],
                      result: result,
                      index: index,
                    );
                  },
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  int _itemCount(ReportResult result) {
    final shown = _visible.clamp(0, result.rows.length);
    return shown + (shown < result.rows.length ? 1 : 0);
  }

  Widget _moreButton(ReportResult result) {
    final remaining = result.rows.length - _visible;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: OutlinedButton(
        onPressed: () => setState(() => _visible += _pageSize),
        child: Text('Show more ($remaining left)'),
      ),
    );
  }

  Widget _errorCard() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: StatusCard(
        accentColor: AppColors.danger,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'The report did not run',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 4),
            Text(
              _error!,
              style: const TextStyle(fontSize: 12.5, color: AppColors.textSoft),
            ),
            const SizedBox(height: 10),
            FilledButton(
              onPressed: _running ? null : _run,
              style: FilledButton.styleFrom(
                minimumSize: const Size(0, 40),
                padding: const EdgeInsets.symmetric(horizontal: 20),
              ),
              child: const Text('Try again'),
            ),
          ],
        ),
      ),
    );
  }
}

/// The active filters, always visible, always editable.
class _FilterBar extends StatelessWidget {
  const _FilterBar({
    required this.def,
    required this.filters,
    required this.result,
    required this.running,
    required this.onEdit,
  });

  final ReportDef def;
  final ReportFilters filters;
  final ReportResult? result;
  final bool running;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    return StatusCard(
      accentColor: running ? AppColors.info : AppColors.accent,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  filters.summary(def),
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              TextButton.icon(
                onPressed: running ? null : onEdit,
                icon: const Icon(Icons.tune_rounded, size: 16),
                label: const Text('Filters'),
                style: TextButton.styleFrom(
                  minimumSize: const Size(0, 34),
                  padding: const EdgeInsets.symmetric(horizontal: 10),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ),
            ],
          ),
          if (result != null) ...[
            const SizedBox(height: 6),
            Text(
              // Every result is stamped. Without it there is no way to tell a
              // number pulled a second ago from one pulled this morning.
              '${ReportFormatter.compact(result!.rows.length)} rows · '
              'fetched ${_time(result!.fetchedAt)}',
              style: const TextStyle(
                fontSize: 11.5,
                color: AppColors.textMuted,
              ),
            ),
          ],
          if (running)
            const Padding(
              padding: EdgeInsets.only(top: 10),
              child: ClipRRect(
                borderRadius: BorderRadius.all(Radius.circular(4)),
                child: LinearProgressIndicator(minHeight: 3),
              ),
            ),
        ],
      ),
    );
  }

  static String _time(DateTime? t) {
    if (t == null) return 'just now';
    final diff = DateTime.now().difference(t);
    if (diff.inSeconds < 45) return 'just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes} min ago';
    if (diff.inHours < 24) return '${diff.inHours} h ago';
    return '${diff.inDays} d ago';
  }
}

/// Shown above a report served from the local cache.
///
/// It names the age rather than saying "offline", because the question a reader
/// actually has is not "is there signal" but "how old are these numbers" — and
/// that is the difference between a figure they can act on and one they cannot.
class _StaleBanner extends StatelessWidget {
  const _StaleBanner({required this.fetchedAt});

  final DateTime? fetchedAt;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      color: AppColors.warningSunk,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(
        children: [
          const Icon(
            Icons.history_rounded,
            size: 16,
            color: AppColors.warningInk,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              fetchedAt == null
                  ? 'Saved figures — could not reach the server.'
                  : 'Saved figures from ${_age(fetchedAt!)} — could not reach '
                      'the server. Pull down to try again.',
              style: const TextStyle(
                fontSize: 12.5,
                height: 1.25,
                color: AppColors.warningInk,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }

  static String _age(DateTime at) {
    final gap = DateTime.now().difference(at);
    if (gap.inMinutes < 1) return 'a moment ago';
    if (gap.inMinutes < 60) return '${gap.inMinutes} min ago';
    if (gap.inHours < 24) {
      return '${gap.inHours} hour${gap.inHours == 1 ? '' : 's'} ago';
    }
    return '${gap.inDays} day${gap.inDays == 1 ? '' : 's'} ago';
  }
}
