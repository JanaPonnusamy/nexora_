import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/time_report/domain/time_report_models.dart';

/// Client for `/api/time-report/*`.
///
/// This module talks to the Matrix COSEC database, which is a separate box
/// from the platform SQL Server. When it is unreachable the server answers
/// **503** with a plain message rather than an error envelope, so a 503 here
/// means "attendance system down", not "you are logged out" — the screen says
/// exactly that instead of a generic failure.
class TimeReportApi {
  const TimeReportApi(this._dio);

  final Dio _dio;

  static const String _base = '/api/time-report';

  Future<TimeReportMeta> meta() async {
    try {
      final res = await _dio.get<Map<String, dynamic>>('$_base/meta');
      return TimeReportMeta.fromJson(res.data ?? const {});
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Runs one of the flat, row-shaped reports.
  Future<TimeReportResult> runTabular(
    TimeReportKind kind,
    TimeReportFilters filters,
  ) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        '$_base/${kind.key}',
        queryParameters: _query(kind, filters),
      );
      return TimeReportResult.fromJson(res.data ?? const {});
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// The daily report, grouped by department.
  Future<DailyAttendance> runDaily(TimeReportFilters filters) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        '$_base/daily',
        queryParameters: _query(TimeReportKind.daily, filters),
      );
      return DailyAttendance.fromJson(res.data ?? const {});
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Downloads the server-built xlsx for a report.
  ///
  /// The styling — status colours, legend, merged headers — is produced by
  /// `excel_export.py`. Rebuilding it on the device would drift from the
  /// desktop export the same team already reads, so the bytes are fetched
  /// rather than generated.
  Future<List<int>> exportXlsx(
    TimeReportKind kind,
    TimeReportFilters filters,
  ) async {
    try {
      final res = await _dio.get<List<int>>(
        '$_base/${kind.key}',
        queryParameters: {..._query(kind, filters), 'export': 'xlsx'},
        options: Options(responseType: ResponseType.bytes),
      );
      return res.data ?? const [];
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Only the parameters a given report actually reads. `date` is aliased on
  /// the server (the handler parameter is `date_`), so the wire name matters.
  static Map<String, dynamic> _query(
    TimeReportKind kind,
    TimeReportFilters filters,
  ) =>
      {
        if (kind.needsSingleDate && filters.date != null)
          'date': _date(filters.date!),
        if (kind.needsDateRange && filters.start != null)
          'start': _date(filters.start!),
        if (kind.needsDateRange && filters.end != null)
          'end': _date(filters.end!),
        if (kind.needsMonth && filters.year != null) 'year': filters.year,
        if (kind.needsMonth && filters.month != null) 'month': filters.month,
        if (kind.needsDays && filters.days != null) 'days': filters.days,
        if (kind.hasModes) 'mode': filters.summaryMode ? 'summary' : 'detail',
        if (filters.departmentId != null) 'dept_id': filters.departmentId,
        if (filters.userId != null) 'user_id': filters.userId,
      };

  static String _date(DateTime d) => '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';
}
