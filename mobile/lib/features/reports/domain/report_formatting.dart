import 'package:nexora_mobile/features/reports/domain/report_models.dart';

/// Renders a raw report cell the way its column asks for.
///
/// The reports SQL returns numbers as `Decimal`, which FastAPI serialises as
/// **strings**, and dates as ISO strings. Formatting therefore has to parse
/// before it can format, and must fall back to showing the raw value rather
/// than a blank — a number the app cannot parse is still information the user
/// can read, whereas an empty cell looks like missing data.
class ReportFormatter {
  const ReportFormatter._();

  static String cell(Object? value, ReportColumn column) {
    if (value == null) return '—';
    return switch (column.format) {
      ReportFormat.money => money(value),
      ReportFormat.int_ => integer(value),
      ReportFormat.date => date(value),
      ReportFormat.text => value.toString(),
    };
  }

  /// Two decimals with thousands separators. Indian grouping is deliberately
  /// not used: the web console shows plain thousands and the two must agree.
  static String money(Object? value) {
    final n = _toNum(value);
    if (n == null) return value?.toString() ?? '—';
    return _group(n.toStringAsFixed(2));
  }

  static String integer(Object? value) {
    final n = _toNum(value);
    if (n == null) return value?.toString() ?? '—';
    return _group(n.round().toString());
  }

  /// `dd MMM yy`. Compact enough for a phone column without losing the year,
  /// which matters on expiry and last-sale dates.
  static String date(Object? value) {
    if (value == null) return '—';
    final raw = value.toString();
    final parsed = DateTime.tryParse(raw);
    if (parsed == null) return raw;
    return '${parsed.day.toString().padLeft(2, '0')} '
        '${_months[parsed.month - 1]} '
        '${(parsed.year % 100).toString().padLeft(2, '0')}';
  }

  /// Compact form for the summary strip: 1.2k, 3.4M.
  static String compact(Object? value) {
    final n = _toNum(value);
    if (n == null) return value?.toString() ?? '—';
    final abs = n.abs();
    if (abs < 1000) return n.round().toString();
    if (abs < 1000000) return '${(n / 1000).toStringAsFixed(1)}k';
    return '${(n / 1000000).toStringAsFixed(1)}M';
  }

  static num? _toNum(Object? value) => switch (value) {
        final num n => n,
        final String s => num.tryParse(s.trim()),
        _ => null,
      };

  /// Thousands separators, applied to the integer part only.
  static String _group(String number) {
    final negative = number.startsWith('-');
    final body = negative ? number.substring(1) : number;
    final dot = body.indexOf('.');
    final whole = dot == -1 ? body : body.substring(0, dot);
    final fraction = dot == -1 ? '' : body.substring(dot);

    final buffer = StringBuffer();
    for (var i = 0; i < whole.length; i++) {
      if (i > 0 && (whole.length - i) % 3 == 0) buffer.write(',');
      buffer.write(whole[i]);
    }
    return '${negative ? '-' : ''}$buffer$fraction';
  }

  static const _months = [
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
  ];
}

/// Renders a result as CSV for sharing.
///
/// CSV rather than xlsx because there is no server-side export for this module
/// — the reports API returns data, not files — and a CSV a buyer can open in
/// Excel beats no export at all. Values are quoted defensively: product names
/// in this catalog contain commas routinely.
String reportToCsv(ReportResult result) {
  final buffer = StringBuffer();
  buffer.writeln(result.columns.map((c) => _csv(c.label)).join(','));
  for (final row in result.rows) {
    buffer.writeln(
      result.columns.map((c) => _csv(row[c.key]?.toString() ?? '')).join(','),
    );
  }
  return buffer.toString();
}

String _csv(String value) {
  if (!value.contains(RegExp(r'[",\n\r]'))) return value;
  return '"${value.replaceAll('"', '""')}"';
}
