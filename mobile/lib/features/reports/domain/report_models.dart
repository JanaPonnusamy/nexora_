/// Models for `/api/reports/*`.
///
/// The module is genuinely catalog-driven: `GET /api/reports` returns the list
/// of reports *and which inputs each one needs*, and every report comes back in
/// one uniform shape. That is why mobile needs no per-report screen — the
/// filter sheet and the grid are both generated from this metadata, and a
/// report added on the server appears here without an app release.
library;

/// How a column should be rendered, from `ReportColumn.format` on the server.
enum ReportFormat {
  money,
  int_,
  date,
  text;

  static ReportFormat fromWire(String? value) => switch (value) {
        'money' => ReportFormat.money,
        'int' => ReportFormat.int_,
        'date' => ReportFormat.date,
        _ => ReportFormat.text,
      };

  /// The server's spelling, not the Dart name — `int_` exists only because
  /// `int` is a reserved word here, and writing that into the cache would not
  /// read back.
  String get wire => this == ReportFormat.int_ ? 'int' : name;
}

/// Horizontal alignment the server asks for. Numbers come back right-aligned,
/// which is the difference between a scannable column and a ragged one.
enum ReportAlign {
  left,
  right,
  center;

  static ReportAlign fromWire(String? value) => switch (value) {
        'right' => ReportAlign.right,
        'center' => ReportAlign.center,
        _ => ReportAlign.left,
      };
}

class ReportColumn {
  const ReportColumn({
    required this.key,
    required this.label,
    this.align = ReportAlign.left,
    this.format = ReportFormat.text,
  });

  final String key;
  final String label;
  final ReportAlign align;
  final ReportFormat format;

  factory ReportColumn.fromJson(Map<String, dynamic> json) => ReportColumn(
        key: json['key']?.toString() ?? '',
        label: json['label']?.toString() ?? json['key']?.toString() ?? '',
        align: ReportAlign.fromWire(json['align']?.toString()),
        format: ReportFormat.fromWire(json['format']?.toString()),
      );

  bool get isNumeric =>
      format == ReportFormat.money || format == ReportFormat.int_;

  /// Wire-shaped, so a cached column reads back through [fromJson] unchanged.
  Map<String, dynamic> toCacheJson() => {
        'key': key,
        'label': label,
        'align': align.name,
        'format': format.wire,
      };
}

/// One entry in the report catalog, including which filters it requires.
class ReportDef {
  const ReportDef({
    required this.key,
    required this.label,
    required this.group,
    this.needsDateRange = false,
    this.needsDwellDays = false,
    this.needsSupplier = false,
    this.needsDivision = false,
  });

  final String key;
  final String label;

  /// Server-side grouping ("Sales", "Margin", "Stock") — used to section the
  /// catalog list rather than showing eight flat rows.
  final String group;

  final bool needsDateRange;
  final bool needsDwellDays;
  final bool needsSupplier;
  final bool needsDivision;

  factory ReportDef.fromJson(Map<String, dynamic> json) => ReportDef(
        key: json['key']?.toString() ?? '',
        label: json['label']?.toString() ?? json['key']?.toString() ?? '',
        group: json['group']?.toString() ?? 'Reports',
        needsDateRange: json['needs_date_range'] == true,
        needsDwellDays: json['needs_dwell_days'] == true,
        needsSupplier: json['needs_supplier'] == true,
        needsDivision: json['needs_division'] == true,
      );

  /// True when the report can be run without asking the user anything.
  bool get runsImmediately =>
      !needsDateRange && !needsDwellDays && !needsDivision;

  /// Supplier is a *filter*, not a requirement — the server treats a null
  /// `supplier_code` as "all suppliers", so it never blocks a run.
  bool get hasOptionalFilters => needsSupplier;
}

/// The filters a run was issued with. Kept as one object so a result can be
/// stamped with exactly what produced it.
class ReportFilters {
  const ReportFilters({
    this.from,
    this.to,
    this.dwellDays,
    this.supplierCode,
    this.supplierName,
    this.divisionCode,
  });

  final DateTime? from;
  final DateTime? to;
  final int? dwellDays;
  final String? supplierCode;
  final String? supplierName;
  final String? divisionCode;

  ReportFilters copyWith({
    DateTime? from,
    DateTime? to,
    int? dwellDays,
    String? supplierCode,
    String? supplierName,
    String? divisionCode,
    bool clearSupplier = false,
  }) =>
      ReportFilters(
        from: from ?? this.from,
        to: to ?? this.to,
        dwellDays: dwellDays ?? this.dwellDays,
        supplierCode:
            clearSupplier ? null : (supplierCode ?? this.supplierCode),
        supplierName:
            clearSupplier ? null : (supplierName ?? this.supplierName),
        divisionCode: divisionCode ?? this.divisionCode,
      );

  /// Sensible starting point for a report that wants a range: the current
  /// month to date, which is what someone opening a sales report usually means.
  static ReportFilters defaultsFor(ReportDef def, {DateTime? now}) {
    final today = now ?? DateTime.now();
    return ReportFilters(
      from: def.needsDateRange ? DateTime(today.year, today.month, 1) : null,
      to: def.needsDateRange ? today : null,
      dwellDays: def.needsDwellDays ? 120 : null,
    );
  }

  /// True when every input the report requires has a value.
  bool satisfies(ReportDef def) {
    if (def.needsDateRange && (from == null || to == null)) return false;
    if (def.needsDwellDays && dwellDays == null) return false;
    if (def.needsDivision && (divisionCode ?? '').isEmpty) return false;
    return true;
  }

  /// Short human summary shown under the report title.
  String summary(ReportDef def) {
    final parts = <String>[
      if (def.needsDateRange && from != null && to != null)
        '${_d(from!)} – ${_d(to!)}',
      if (def.needsDwellDays && dwellDays != null) '$dwellDays days idle',
      if (supplierName != null) supplierName!,
      if (def.needsDivision && divisionCode != null) divisionCode!,
    ];
    return parts.isEmpty ? 'No filters' : parts.join(' · ');
  }

  static String _d(DateTime d) =>
      '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}';
}

/// A supplier option for the Non-Moving / Purchased-Not-Sold filter.
class SupplierOption {
  const SupplierOption({required this.code, this.name});

  final String code;
  final String? name;

  factory SupplierOption.fromJson(Map<String, dynamic> json) => SupplierOption(
        code: json['supplier_code']?.toString() ?? '',
        name: json['supplier_name']?.toString(),
      );

  String get label => name?.trim().isNotEmpty == true ? name!.trim() : code;
}

/// A completed run: the uniform result every report returns.
class ReportResult {
  const ReportResult({
    required this.report,
    required this.title,
    required this.columns,
    required this.rows,
    this.summary,
    this.fetchedAt,
  });

  final String report;
  final String title;
  final List<ReportColumn> columns;
  final List<Map<String, dynamic>> rows;

  /// Optional totals row the legacy WinForms reports showed.
  final Map<String, dynamic>? summary;

  /// When this client received it — a cached result must always be stamped, or
  /// a reader has no way to tell yesterday's numbers from today's.
  final DateTime? fetchedAt;

  factory ReportResult.fromJson(
    Map<String, dynamic> json, {
    DateTime? fetchedAt,
  }) =>
      ReportResult(
        report: json['report']?.toString() ?? '',
        title: json['title']?.toString() ?? '',
        columns: (json['columns'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(ReportColumn.fromJson)
            .toList(growable: false),
        rows: (json['rows'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .toList(growable: false),
        summary: json['summary'] as Map<String, dynamic>?,
        fetchedAt: fetchedAt ?? DateTime.now(),
      );

  /// Round-trip form for the offline cache.
  ///
  /// Mirrors the server's shape rather than inventing one, so a cached payload
  /// reads back through [ReportResult.fromJson] unchanged — the catalogue is
  /// server-driven and a report gains columns without an app release, so any
  /// hand-written schema here would go stale by design. `fetchedAt` is not
  /// included: it belongs to the cache row, and storing it twice invites the
  /// two copies to disagree.
  Map<String, dynamic> toCacheJson() => {
        'report': report,
        'title': title,
        'columns': columns.map((c) => c.toCacheJson()).toList(growable: false),
        'rows': rows,
        if (summary != null) 'summary': summary,
      };

  ReportResult copyWithFetchedAt(DateTime at) => ReportResult(
        report: report,
        title: title,
        columns: columns,
        rows: rows,
        summary: summary,
        fetchedAt: at,
      );

  bool get isEmpty => rows.isEmpty;

  /// The column to lead each row card with — the first non-numeric one, which
  /// is the product/supplier/date name in every report in the catalog.
  ReportColumn? get primaryColumn {
    for (final c in columns) {
      if (!c.isNumeric) return c;
    }
    return columns.isEmpty ? null : columns.first;
  }

  /// The remaining columns, in server order.
  List<ReportColumn> get detailColumns {
    final primary = primaryColumn;
    return columns.where((c) => c.key != primary?.key).toList(growable: false);
  }
}
