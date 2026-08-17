/// Models for `/api/time-report/*` — attendance over the Matrix COSEC
/// database.
///
/// Unlike `/api/reports`, this module does **not** publish column metadata:
/// the server says "the frontend renders each shape with a dedicated view,
/// exactly as the legacy app did". So the column specs live here, on the
/// client, and are the one part of this module that must be kept in step with
/// `modules/time_report/service.py` by hand.
library;

/// Which report to run. Keys match `service.catalog()`.
enum TimeReportKind {
  daily('daily', 'Daily'),
  monthly('monthly', 'Monthly'),
  misspunch('misspunch', 'Miss Punch'),
  user('user', 'User'),
  inactive('inactive', 'Inactive Users');

  const TimeReportKind(this.key, this.label);

  final String key;
  final String label;

  static TimeReportKind? fromKey(String key) {
    for (final k in TimeReportKind.values) {
      if (k.key == key) return k;
    }
    return null;
  }

  /// True for the reports that come back as a flat `rows` list and can share
  /// one renderer.
  bool get isTabular =>
      this == TimeReportKind.misspunch ||
      this == TimeReportKind.user ||
      this == TimeReportKind.inactive;

  bool get needsDateRange =>
      this == TimeReportKind.misspunch || this == TimeReportKind.user;

  bool get needsSingleDate => this == TimeReportKind.daily;

  bool get needsMonth => this == TimeReportKind.monthly;

  bool get needsDays => this == TimeReportKind.inactive;

  /// Only the User report has summary/detail modes.
  bool get hasModes => this == TimeReportKind.user;
}

/// One column of a tabular report.
class TimeColumn {
  const TimeColumn(this.key, this.label, {this.numeric = false});

  final String key;
  final String label;
  final bool numeric;
}

/// Column specs, mirroring the xlsx headers the server builds for each report
/// so a shared export and an on-screen card show the same fields.
class TimeReportColumns {
  const TimeReportColumns._();

  static const misspunch = [
    TimeColumn('pdate_str', 'Date'),
    TimeColumn('user_id', 'User ID'),
    TimeColumn('name', 'Name'),
    TimeColumn('department', 'Department'),
    TimeColumn('punch_count', '#Punch', numeric: true),
    TimeColumn('work_hm', 'Work'),
  ];

  static const userSummary = [
    TimeColumn('user_id', 'User ID'),
    TimeColumn('name', 'Name'),
    TimeColumn('department', 'Department'),
    TimeColumn('present', 'Present', numeric: true),
    TimeColumn('full', 'Full', numeric: true),
    TimeColumn('short', 'Short', numeric: true),
    TimeColumn('low', 'Low', numeric: true),
    TimeColumn('miss_punch', 'Miss', numeric: true),
    TimeColumn('absent', 'Absent', numeric: true),
    TimeColumn('late', 'Late', numeric: true),
    TimeColumn('total_hm', 'Total Hrs'),
  ];

  static const userDetail = [
    TimeColumn('pdate_str', 'Date'),
    TimeColumn('user_id', 'User ID'),
    TimeColumn('name', 'Name'),
    TimeColumn('work_hm', 'Work'),
    TimeColumn('late_in', 'Late'),
  ];

  static const inactive = [
    TimeColumn('user_id', 'User ID'),
    TimeColumn('name', 'Name'),
    TimeColumn('department', 'Department'),
    TimeColumn('join_dt', 'Joined'),
    TimeColumn('last_seen', 'Last punch'),
    TimeColumn('days_since', 'Days since', numeric: true),
  ];

  /// The right spec for a report, accounting for the User report's two modes.
  static List<TimeColumn> forKind(TimeReportKind kind,
          {bool summary = false}) =>
      switch (kind) {
        TimeReportKind.misspunch => misspunch,
        TimeReportKind.user => summary ? userSummary : userDetail,
        TimeReportKind.inactive => inactive,
        _ => const [],
      };

  /// The column that names the row, used as the card's heading.
  static TimeColumn heading(TimeReportKind kind, {bool summary = false}) =>
      switch (kind) {
        TimeReportKind.inactive => const TimeColumn('name', 'Name'),
        TimeReportKind.user when summary => const TimeColumn('name', 'Name'),
        _ => const TimeColumn('name', 'Name'),
      };
}

/// Filters for a time report run.
class TimeReportFilters {
  const TimeReportFilters({
    this.date,
    this.start,
    this.end,
    this.year,
    this.month,
    this.departmentId,
    this.userId,
    this.days,
    this.summaryMode = false,
  });

  final DateTime? date;
  final DateTime? start;
  final DateTime? end;
  final int? year;
  final int? month;
  final String? departmentId;
  final String? userId;

  /// Inactive-report threshold. Null lets the server apply its configured
  /// default rather than this client inventing one.
  final int? days;

  final bool summaryMode;

  static TimeReportFilters defaultsFor(
    TimeReportKind kind, {
    DateTime? now,
  }) {
    final today = now ?? DateTime.now();
    return TimeReportFilters(
      date: kind.needsSingleDate ? today : null,
      start: kind.needsDateRange ? DateTime(today.year, today.month, 1) : null,
      end: kind.needsDateRange ? today : null,
      year: kind.needsMonth ? today.year : null,
      month: kind.needsMonth ? today.month : null,
    );
  }

  TimeReportFilters copyWith({
    DateTime? date,
    DateTime? start,
    DateTime? end,
    int? year,
    int? month,
    String? departmentId,
    String? userId,
    int? days,
    bool? summaryMode,
    bool clearDepartment = false,
    bool clearUser = false,
  }) =>
      TimeReportFilters(
        date: date ?? this.date,
        start: start ?? this.start,
        end: end ?? this.end,
        year: year ?? this.year,
        month: month ?? this.month,
        departmentId:
            clearDepartment ? null : (departmentId ?? this.departmentId),
        userId: clearUser ? null : (userId ?? this.userId),
        days: days ?? this.days,
        summaryMode: summaryMode ?? this.summaryMode,
      );

  String summary(TimeReportKind kind, {String? departmentName}) {
    final parts = <String>[
      if (kind.needsSingleDate && date != null) _d(date!),
      if (kind.needsDateRange && start != null && end != null)
        '${_d(start!)} – ${_d(end!)}',
      if (kind.needsMonth && year != null && month != null)
        '${_month(month!)} $year',
      if (kind.needsDays) '${days ?? 30}+ days idle',
      if (kind.hasModes) summaryMode ? 'Summary' : 'Detail',
      if (departmentName != null) departmentName,
    ];
    return parts.isEmpty ? 'Defaults' : parts.join(' · ');
  }

  static String _d(DateTime d) =>
      '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}';

  static String _month(int m) => const [
        'Jan',
        'Feb',
        'Mar',
        'Apr',
        'May',
        'Jun',
        'Jul',
        'Aug',
        'Sep',
        'Oct',
        'Nov',
        'Dec',
      ][(m - 1).clamp(0, 11)];
}

/// A department option from `/meta`.
class TimeDepartment {
  const TimeDepartment({required this.id, this.name});

  final String id;
  final String? name;

  factory TimeDepartment.fromJson(Map<String, dynamic> json) => TimeDepartment(
        // DPTID is numeric in COSEC but is sent as a query string, so it is
        // carried as a string end to end.
        id: json['DPTID']?.toString() ?? '',
        name: json['Name']?.toString(),
      );

  String get label => (name?.trim().isNotEmpty ?? false) ? name!.trim() : id;
}

/// Report metadata: the catalog plus the filter options.
class TimeReportMeta {
  const TimeReportMeta({
    this.reports = const [],
    this.departments = const [],
    this.minDate,
    this.maxDate,
  });

  final List<TimeReportKind> reports;
  final List<TimeDepartment> departments;
  final DateTime? minDate;
  final DateTime? maxDate;

  factory TimeReportMeta.fromJson(Map<String, dynamic> json) {
    final bounds = json['bounds'];
    return TimeReportMeta(
      reports: (json['reports'] as List? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map((r) => TimeReportKind.fromKey(r['key']?.toString() ?? ''))
          .whereType<TimeReportKind>()
          .toList(growable: false),
      departments: (json['departments'] as List? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(TimeDepartment.fromJson)
          .where((d) => d.id.isNotEmpty)
          .toList(growable: false),
      minDate: bounds is Map
          ? DateTime.tryParse(bounds['min']?.toString() ?? '')
          : null,
      maxDate: bounds is Map
          ? DateTime.tryParse(bounds['max']?.toString() ?? '')
          : null,
    );
  }
}

/// A tabular report result: `{rows, count, legend?}`.
class TimeReportResult {
  const TimeReportResult({
    this.title,
    this.rows = const [],
    this.count = 0,
    this.fetchedAt,
  });

  final String? title;
  final List<Map<String, dynamic>> rows;
  final int count;
  final DateTime? fetchedAt;

  factory TimeReportResult.fromJson(Map<String, dynamic> json) =>
      TimeReportResult(
        title: json['title']?.toString(),
        rows: (json['rows'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .toList(growable: false),
        count: switch (json['count']) {
          final int i => i,
          final num n => n.toInt(),
          _ => (json['rows'] as List? ?? const []).length,
        },
        fetchedAt: DateTime.now(),
      );

  bool get isEmpty => rows.isEmpty;
}

/// The daily report, which is grouped by department rather than flat.
class DailyAttendance {
  const DailyAttendance({
    this.title,
    this.dateLabel,
    this.departments = const [],
    this.fetchedAt,
  });

  final String? title;
  final String? dateLabel;
  final List<DailyDepartment> departments;
  final DateTime? fetchedAt;

  factory DailyAttendance.fromJson(Map<String, dynamic> json) =>
      DailyAttendance(
        title: json['title']?.toString(),
        dateLabel: json['date_fmt']?.toString(),
        departments: (json['departments'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(DailyDepartment.fromJson)
            .toList(growable: false),
        fetchedAt: DateTime.now(),
      );

  bool get isEmpty => departments.isEmpty;

  int get totalRows => departments.fold(0, (sum, d) => sum + d.rows.length);
}

class DailyDepartment {
  const DailyDepartment({
    required this.name,
    this.rows = const [],
    this.totals = const {},
  });

  final String name;
  final List<Map<String, dynamic>> rows;
  final Map<String, dynamic> totals;

  factory DailyDepartment.fromJson(Map<String, dynamic> json) =>
      DailyDepartment(
        name: json['name']?.toString() ?? '—',
        rows: (json['rows'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .toList(growable: false),
        totals: (json['totals'] as Map?)?.cast<String, dynamic>() ?? const {},
      );
}
