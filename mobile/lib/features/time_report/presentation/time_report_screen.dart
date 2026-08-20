import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/time_report/data/time_report_api.dart';
import 'package:nexora_mobile/features/time_report/domain/time_report_models.dart';

final timeReportApiProvider = Provider<TimeReportApi>(
  (ref) => TimeReportApi(ref.watch(dioProvider)),
);

final timeReportMetaProvider = FutureProvider<TimeReportMeta>(
  (ref) => ref.watch(timeReportApiProvider).meta(),
);

/// Attendance reports from the COSEC system.
///
/// Four of the five report kinds are here. The monthly muster grid is
/// deliberately absent — it is a day-by-day colour matrix per user, which does
/// not survive a phone-width layout; that one stays on the desktop console and
/// the xlsx export covers the mobile need.
class TimeReportScreen extends ConsumerStatefulWidget {
  const TimeReportScreen({super.key});

  @override
  ConsumerState<TimeReportScreen> createState() => _TimeReportScreenState();
}

class _TimeReportScreenState extends ConsumerState<TimeReportScreen> {
  final _log = AppLogger.of('TimeReport');

  TimeReportKind _kind = TimeReportKind.daily;
  late TimeReportFilters _filters = TimeReportFilters.defaultsFor(_kind);

  TimeReportResult? _tabular;
  DailyAttendance? _daily;
  String? _error;
  bool _busy = false;
  bool _exporting = false;

  static const int _pageSize = 40;
  int _visible = _pageSize;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _run());
  }

  void _selectKind(TimeReportKind kind) {
    setState(() {
      _kind = kind;
      _filters = TimeReportFilters.defaultsFor(kind);
      _tabular = null;
      _daily = null;
      _error = null;
      _visible = _pageSize;
    });
    _run();
  }

  Future<void> _run() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = ref.read(timeReportApiProvider);
      if (_kind == TimeReportKind.daily) {
        final daily = await api.runDaily(_filters);
        if (mounted) setState(() => _daily = daily);
      } else {
        final result = await api.runTabular(_kind, _filters);
        if (mounted) {
          setState(() {
            _tabular = result;
            _visible = _pageSize;
          });
        }
      }
    } on ApiException catch (e) {
      _log.warning('${_kind.key} failed: ${e.message}');
      if (mounted) {
        setState(
          () => _error = e.statusCode == 503
              // The COSEC box is separate infrastructure; naming it saves a
              // support call that would otherwise blame this app.
              ? 'The attendance system is not reachable right now.\n'
                  '${e.message}'
              : e.message,
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _export() async {
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _exporting = true);
    try {
      final bytes =
          await ref.read(timeReportApiProvider).exportXlsx(_kind, _filters);
      if (bytes.isEmpty) {
        messenger.showSnackBar(
          const SnackBar(content: Text('The export came back empty.')),
        );
        return;
      }
      final dir = await getTemporaryDirectory();
      final name = '${_kind.key}_${DateTime.now().millisecondsSinceEpoch}.xlsx';
      final file = File('${dir.path}/$name');
      await file.writeAsBytes(bytes, flush: true);

      await Share.shareXFiles(
        [
          XFile(
            file.path,
            mimeType: 'application/vnd.openxmlformats-officedocument'
                '.spreadsheetml.sheet',
          ),
        ],
        subject: '${_kind.label} — ${_filters.summary(_kind)}',
      );
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    } on Object catch (e) {
      _log.warning('Export failed: $e');
      messenger.showSnackBar(
        const SnackBar(content: Text('Could not export the report.')),
      );
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  Future<void> _editFilters() async {
    final meta = await ref.read(timeReportMetaProvider.future);
    if (!mounted) return;
    final updated = await showModalBottomSheet<TimeReportFilters>(
      context: context,
      backgroundColor: AppColors.surfaceRaised,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _FilterSheet(
        kind: _kind,
        filters: _filters,
        departments: meta.departments,
      ),
    );
    if (updated == null || !mounted) return;
    setState(() => _filters = updated);
    await _run();
  }

  bool get _hasResult =>
      (_tabular != null && !_tabular!.isEmpty) ||
      (_daily != null && !_daily!.isEmpty);

  @override
  Widget build(BuildContext context) {
    // The monthly muster grid is intentionally not offered here.
    final offered = TimeReportKind.values
        .where((k) => k != TimeReportKind.monthly)
        .toList(growable: false);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Time Report'),
        actions: [
          if (_hasResult)
            IconButton(
              onPressed: _exporting ? null : _export,
              icon: _exporting
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2.2),
                    )
                  : const Icon(Icons.ios_share_rounded),
              tooltip: 'Export as Excel',
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _run,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
          children: [
            SizedBox(
              height: 38,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: offered.length,
                separatorBuilder: (_, __) => const SizedBox(width: 8),
                itemBuilder: (context, i) => ChoiceChip(
                  label: Text(offered[i].label),
                  selected: _kind == offered[i],
                  onSelected: (_) => _selectKind(offered[i]),
                ),
              ),
            ),
            const SizedBox(height: 12),
            _filterBar(),
            if (_error != null) ...[
              const SizedBox(height: 12),
              _errorCard(),
            ] else if (_busy && !_hasResult) ...[
              const SizedBox(height: 40),
              const InlineLoading(),
            ] else ...[
              const SizedBox(height: 12),
              ..._results(),
            ],
          ],
        ),
      ),
    );
  }

  List<Widget> _results() {
    if (_kind == TimeReportKind.daily) {
      final daily = _daily;
      if (daily == null) return const [];
      if (daily.isEmpty) {
        return const [
          EmptyState(
            message: 'No attendance recorded for that date.',
            icon: Icons.event_busy_outlined,
          ),
        ];
      }
      return [
        for (final dept in daily.departments) ...[
          SectionHeader(
            title: '${dept.name.toUpperCase()} (${dept.rows.length})',
            icon: Icons.apartment_rounded,
          ),
          for (final row in dept.rows) _AttendanceCard(row: row),
          const SizedBox(height: 12),
        ],
      ];
    }

    final result = _tabular;
    if (result == null) return const [];
    if (result.isEmpty) {
      return const [
        EmptyState(
          message: 'No rows matched these filters.',
          icon: Icons.filter_alt_off_outlined,
        ),
      ];
    }

    final columns = TimeReportColumns.forKind(
      _kind,
      summary: _filters.summaryMode,
    );
    final shown = _visible.clamp(0, result.rows.length);
    return [
      for (var i = 0; i < shown; i++)
        _RowCard(row: result.rows[i], columns: columns),
      if (shown < result.rows.length)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: OutlinedButton(
            onPressed: () => setState(() => _visible += _pageSize),
            child: Text('Show more (${result.rows.length - shown} left)'),
          ),
        ),
    ];
  }

  Widget _filterBar() {
    final count = _kind == TimeReportKind.daily
        ? _daily?.totalRows
        : _tabular?.rows.length;

    return StatusCard(
      accentColor: _busy ? AppColors.info : AppColors.accent,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  _filters.summary(_kind),
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              TextButton.icon(
                onPressed: _busy ? null : _editFilters,
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
          if (count != null) ...[
            const SizedBox(height: 6),
            Text(
              '$count row${count == 1 ? '' : 's'}',
              style: const TextStyle(
                fontSize: 11.5,
                color: AppColors.textMuted,
              ),
            ),
          ],
          if (_busy)
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

  Widget _errorCard() {
    return StatusCard(
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
            onPressed: _busy ? null : _run,
            style: FilledButton.styleFrom(
              minimumSize: const Size(0, 40),
              padding: const EdgeInsets.symmetric(horizontal: 20),
            ),
            child: const Text('Try again'),
          ),
        ],
      ),
    );
  }
}

/// A tabular row, rendered as a card with a heading and wrapping fields.
class _RowCard extends StatelessWidget {
  const _RowCard({required this.row, required this.columns});

  final Map<String, dynamic> row;
  final List<TimeColumn> columns;

  @override
  Widget build(BuildContext context) {
    if (columns.isEmpty) return const SizedBox.shrink();
    final heading = columns.firstWhere(
      (c) => c.key == 'name',
      orElse: () => columns.first,
    );
    final rest = columns.where((c) => c.key != heading.key);

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.rule),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${row[heading.key] ?? '—'}',
            style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 16,
            runSpacing: 8,
            children: [
              for (final column in rest)
                if (_has(row[column.key]))
                  _Field(label: column.label, value: '${row[column.key]}'),
            ],
          ),
          if (row['punches'] is List && (row['punches'] as List).isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                (row['punches'] as List).join('  ·  '),
                style: const TextStyle(
                  fontSize: 11.5,
                  color: AppColors.textMuted,
                  fontFeatures: [FontFeature.tabularFigures()],
                ),
              ),
            ),
        ],
      ),
    );
  }

  static bool _has(Object? v) =>
      v != null && v.toString().trim().isNotEmpty && v.toString() != '-';
}

/// One row of the department-grouped daily report.
class _AttendanceCard extends StatelessWidget {
  const _AttendanceCard({required this.row});

  final Map<String, dynamic> row;

  @override
  Widget build(BuildContext context) {
    final status = row['status']?.toString() ?? '';
    final tone = _tone(status);

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.rule),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${row['name'] ?? row['user_id'] ?? '—'}',
                  style: const TextStyle(
                    fontSize: 13.5,
                    fontWeight: FontWeight.w700,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (status.isNotEmpty)
                StatusBadge(label: status, color: tone, dense: true),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 16,
            runSpacing: 8,
            children: [
              if (row['user_id'] != null)
                _Field(label: 'User ID', value: '${row['user_id']}'),
              if (row['work_hm'] != null)
                _Field(label: 'Work', value: '${row['work_hm']}'),
              if (_present(row['late_in']))
                _Field(label: 'Late', value: '${row['late_in']}'),
            ],
          ),
          if (row['punches'] is List && (row['punches'] as List).isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                (row['punches'] as List).join('  ·  '),
                style: const TextStyle(
                  fontSize: 11.5,
                  color: AppColors.textMuted,
                  fontFeatures: [FontFeature.tabularFigures()],
                ),
              ),
            ),
        ],
      ),
    );
  }

  static bool _present(Object? v) =>
      v != null && v.toString().trim().isNotEmpty;

  /// The server sends a status hex per row, but mapping to the app palette
  /// keeps the screen consistent with the rest of the product rather than
  /// importing the legacy report's colours.
  static Color _tone(String status) {
    final s = status.toUpperCase();
    if (s.contains('ABSENT')) return AppColors.danger;
    if (s.contains('MISS')) return AppColors.warning;
    if (s.contains('SHORT') || s.contains('LOW')) return AppColors.warning;
    if (s.contains('LATE')) return AppColors.info;
    return AppColors.success;
  }
}

class _Field extends StatelessWidget {
  const _Field({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          label,
          style: const TextStyle(fontSize: 10.5, color: AppColors.textMuted),
        ),
        const SizedBox(height: 1),
        Text(
          value,
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
        ),
      ],
    );
  }
}

class _FilterSheet extends StatefulWidget {
  const _FilterSheet({
    required this.kind,
    required this.filters,
    required this.departments,
  });

  final TimeReportKind kind;
  final TimeReportFilters filters;
  final List<TimeDepartment> departments;

  @override
  State<_FilterSheet> createState() => _FilterSheetState();
}

class _FilterSheetState extends State<_FilterSheet> {
  late TimeReportFilters _draft = widget.filters;

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _draft.date ?? now,
      firstDate: DateTime(now.year - 2),
      lastDate: now,
    );
    if (picked == null || !mounted) return;
    setState(() => _draft = _draft.copyWith(date: picked));
  }

  Future<void> _pickRange() async {
    final now = DateTime.now();
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(now.year - 2),
      lastDate: now,
      initialDateRange: (_draft.start != null && _draft.end != null)
          ? DateTimeRange(start: _draft.start!, end: _draft.end!)
          : null,
    );
    if (picked == null || !mounted) return;
    setState(
      () => _draft = _draft.copyWith(start: picked.start, end: picked.end),
    );
  }

  @override
  Widget build(BuildContext context) {
    final kind = widget.kind;

    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        bottom: MediaQuery.viewInsetsOf(context).bottom + 20,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              kind.label,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 16),
            if (kind.needsSingleDate) ...[
              const SectionHeader(title: 'DATE', icon: Icons.event_outlined),
              OutlinedButton.icon(
                onPressed: _pickDate,
                icon: const Icon(Icons.edit_calendar_outlined, size: 18),
                label: Text(
                  _draft.date == null ? 'Choose date' : _long(_draft.date!),
                ),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(46),
                ),
              ),
              const SizedBox(height: 16),
            ],
            if (kind.needsDateRange) ...[
              const SectionHeader(
                title: 'DATE RANGE',
                icon: Icons.date_range_outlined,
              ),
              OutlinedButton.icon(
                onPressed: _pickRange,
                icon: const Icon(Icons.edit_calendar_outlined, size: 18),
                label: Text(
                  (_draft.start != null && _draft.end != null)
                      ? '${_long(_draft.start!)} → ${_long(_draft.end!)}'
                      : 'Choose dates',
                ),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(46),
                ),
              ),
              const SizedBox(height: 16),
            ],
            if (kind.needsDays) ...[
              const SectionHeader(
                title: 'NO PUNCH FOR AT LEAST',
                icon: Icons.hourglass_empty_rounded,
              ),
              Wrap(
                spacing: 8,
                children: [
                  for (final days in [15, 30, 45, 60, 90])
                    ChoiceChip(
                      label: Text('$days d'),
                      selected: _draft.days == days,
                      onSelected: (_) =>
                          setState(() => _draft = _draft.copyWith(days: days)),
                    ),
                ],
              ),
              const SizedBox(height: 16),
            ],
            if (kind.hasModes) ...[
              const SectionHeader(
                  title: 'MODE', icon: Icons.view_agenda_outlined),
              Wrap(
                spacing: 8,
                children: [
                  ChoiceChip(
                    label: const Text('Detail'),
                    selected: !_draft.summaryMode,
                    onSelected: (_) => setState(
                      () => _draft = _draft.copyWith(summaryMode: false),
                    ),
                  ),
                  ChoiceChip(
                    label: const Text('Summary'),
                    selected: _draft.summaryMode,
                    onSelected: (_) => setState(
                      () => _draft = _draft.copyWith(summaryMode: true),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
            ],
            const SectionHeader(
              title: 'DEPARTMENT',
              icon: Icons.apartment_rounded,
            ),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                ChoiceChip(
                  label: const Text('All'),
                  selected: _draft.departmentId == null,
                  onSelected: (_) => setState(
                    () => _draft = _draft.copyWith(clearDepartment: true),
                  ),
                ),
                for (final dept in widget.departments)
                  ChoiceChip(
                    label: Text(dept.label),
                    selected: _draft.departmentId == dept.id,
                    onSelected: (_) => setState(
                      () => _draft = _draft.copyWith(departmentId: dept.id),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () => Navigator.of(context).pop(_draft),
                child: const Text('Run report'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  static String _long(DateTime d) => '${d.day.toString().padLeft(2, '0')}/'
      '${d.month.toString().padLeft(2, '0')}/${d.year}';
}
