/// Small, tolerant JSON coercion helpers shared by the master-data DTOs.
///
/// Backend field names are not fully standardised across modules, so DTOs read
/// the first present key and coerce loosely rather than assuming exact types.
library;

/// Returns the first non-null value among [keys], or null.
Object? firstOf(Map<String, dynamic> json, List<String> keys) {
  for (final k in keys) {
    final v = json[k];
    if (v != null) return v;
  }
  return null;
}

String asString(Object? v, {String fallback = ''}) =>
    v == null ? fallback : v.toString();

String stringField(
  Map<String, dynamic> json,
  List<String> keys, {
  String fallback = '',
}) =>
    asString(firstOf(json, keys), fallback: fallback);

bool asBool(Object? v, {bool fallback = true}) {
  if (v == null) return fallback;
  if (v is bool) return v;
  if (v is num) return v != 0;
  final s = v.toString().trim().toLowerCase();
  if (s.isEmpty) return fallback;
  return s == 'true' || s == '1' || s == 'y' || s == 'yes';
}

int? asIntOrNull(Object? v) {
  if (v == null) return null;
  if (v is int) return v;
  if (v is num) return v.toInt();
  return int.tryParse(v.toString());
}

int asInt(Object? v, {int fallback = 0}) => asIntOrNull(v) ?? fallback;

double asDouble(Object? v, {double fallback = 0}) {
  if (v == null) return fallback;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString()) ?? fallback;
}

DateTime? asDateOrNull(Object? v) {
  if (v == null) return null;
  if (v is DateTime) return v;
  return DateTime.tryParse(v.toString());
}
