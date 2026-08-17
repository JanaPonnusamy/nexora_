import 'dart:io';

import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_review.dart';

/// Typed client for `/api/document-extraction/*`.
///
/// Every path and parameter here was read off `backend/modules/
/// document_extraction/router.py`; nothing is invented. Note the API is
/// tenant-scoped by query parameter (unlike the mobile BFF), so callers must
/// pass `tenantId`.
class DocumentExtractionApi {
  const DocumentExtractionApi(this._dio);

  final Dio _dio;

  static const String _base = '/api/document-extraction';

  /// Uploads one or more page images as a single invoice.
  ///
  /// `group_as_single_invoice` is sent as form data (not a query param) to
  /// match `Form(True)` on the server. Returns the created import ids.
  Future<List<int>> upload({
    required List<File> files,
    required String tenantId,
    String? storeId,
    String? actor,
    bool groupAsSingleInvoice = true,
    void Function(int sent, int total)? onProgress,
    CancelToken? cancelToken,
  }) async {
    try {
      final form = FormData();
      for (final file in files) {
        form.files.add(
          MapEntry(
            'files',
            await MultipartFile.fromFile(
              file.path,
              filename: file.uri.pathSegments.last,
            ),
          ),
        );
      }
      form.fields.add(
        MapEntry('group_as_single_invoice', '$groupAsSingleInvoice'),
      );

      final res = await _dio.post<Map<String, dynamic>>(
        '$_base/imports',
        data: form,
        queryParameters: {
          'tenant_id': tenantId,
          if (storeId != null) 'store_id': storeId,
          if (actor != null) 'actor': actor,
        },
        onSendProgress: onProgress,
        cancelToken: cancelToken,
      );

      final imports = res.data?['imports'];
      if (imports is! List) return const [];
      return imports.map(_importIdOf).whereType<int>().toList(growable: false);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  static int? _importIdOf(Object? entry) {
    if (entry is int) return entry;
    if (entry is Map) {
      final v = entry['import_id'];
      if (v is int) return v;
      if (v is num) return v.toInt();
      if (v is String) return int.tryParse(v);
    }
    return null;
  }

  /// Runs one pipeline stage. The stages are separate endpoints so a failure
  /// can be retried from the point it broke rather than re-running OCR.
  Future<void> runStage(int importId, DocumentStage stage, {String? actor}) =>
      _post('$_base/imports/$importId/${stage.path}', actor: actor);

  /// Full review payload: header, supplier, items and validation.
  Future<DocumentReview> review(int importId) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        '$_base/imports/$importId/review',
      );
      return DocumentReview.fromJson(res.data ?? const {});
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Lightweight status probe used while polling, so a 3-second poll does not
  /// drag the whole review payload over cellular.
  Future<Map<String, dynamic>> importSummary(int importId) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        '$_base/imports/$importId',
      );
      return res.data ?? const {};
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<Map<String, dynamic>> list({
    required String tenantId,
    String? storeId,
    String? status,
    int page = 1,
    int pageSize = 25,
  }) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        '$_base/imports',
        queryParameters: {
          'tenant_id': tenantId,
          if (storeId != null) 'store_id': storeId,
          if (status != null) 'status': status,
          'page': page,
          'page_size': pageSize,
        },
      );
      return res.data ?? const {};
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Partial header update. Only the supplied fields are written.
  Future<void> patchHeader(
    int importId,
    Map<String, dynamic> fields, {
    String? actor,
  }) =>
      _send(
        'PATCH',
        '$_base/imports/$importId/header',
        body: {...fields, if (actor != null) 'actor': actor},
      );

  Future<void> patchItem(
    int importId,
    int itemId,
    Map<String, dynamic> fields, {
    String? actor,
  }) =>
      _send(
        'PATCH',
        '$_base/imports/$importId/items/$itemId',
        body: {...fields, if (actor != null) 'actor': actor},
      );

  /// Marks a line as not part of the invoice (banner text, a footer row the
  /// classifier was unsure about). Excluded rows stay stored.
  Future<void> excludeItem(int importId, int itemId, {String? actor}) =>
      _post('$_base/imports/$importId/items/$itemId/exclude', actor: actor);

  Future<void> assignSupplier(
    int importId,
    Map<String, dynamic> fields, {
    String? actor,
  }) =>
      _send(
        'POST',
        '$_base/imports/$importId/supplier',
        body: {...fields, if (actor != null) 'actor': actor},
      );

  /// Finalises review. Throws with HTTP 409 when unresolved FAILED findings
  /// remain and [force] is false — the caller should surface that, not retry
  /// blindly with force.
  Future<void> save(int importId, {bool force = false, String? actor}) => _send(
        'POST',
        '$_base/imports/$importId/save',
        body: {'force': force, if (actor != null) 'actor': actor},
      );

  /// Builds a workbook for one or more SAVED imports. Returns the batch id and
  /// its download path.
  Future<ExportBatch> createExport({
    required List<int> importIds,
    String fileFormat = 'xlsx',
    String? actor,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '$_base/exports',
        data: {
          'import_ids': importIds,
          'file_format': fileFormat,
          if (actor != null) 'actor': actor,
        },
      );
      return ExportBatch.fromJson(res.data ?? const {});
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Downloads the generated workbook as bytes.
  Future<List<int>> downloadExport(String exportBatchId) async {
    try {
      final res = await _dio.get<List<int>>(
        '$_base/exports/$exportBatchId/download',
        options: Options(responseType: ResponseType.bytes),
      );
      return res.data ?? const [];
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Authenticated path for a page image. Must be fetched with the bearer
  /// header, so a bare `Image.network` will not work — see [imageBytes].
  String previewPath(int importId, {int page = 1}) =>
      '$_base/imports/$importId/preview?page=$page';

  String originalPath(int importId, {int page = 1}) =>
      '$_base/imports/$importId/original?page=$page';

  Future<List<int>> imageBytes(String path) async {
    try {
      final res = await _dio.get<List<int>>(
        path,
        options: Options(responseType: ResponseType.bytes),
      );
      return res.data ?? const [];
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<void> deleteImport(int importId) =>
      _send('DELETE', '$_base/imports/$importId');

  /// Re-runs the pipeline from a stage, reusing everything before it. The
  /// common case is `extraction` after a supplier-layout fix, which avoids
  /// paying for OCR again.
  Future<void> reprocess(
    int importId,
    DocumentStage fromStage, {
    String? actor,
  }) =>
      _send(
        'POST',
        '$_base/imports/$importId/reprocess',
        body: {'from_stage': fromStage.path, if (actor != null) 'actor': actor},
      );

  Future<void> _post(String path, {String? actor}) => _send(
        'POST',
        path,
        query: {if (actor != null) 'actor': actor},
      );

  Future<void> _send(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
  }) async {
    try {
      await _dio.request<dynamic>(
        path,
        data: body,
        queryParameters: query,
        options: Options(method: method),
      );
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}

/// The pipeline stages that can be triggered or resumed from.
enum DocumentStage {
  preprocess('preprocess', 'preprocessing'),
  ocr('ocr', 'ocr'),
  extract('extract', 'extraction'),
  validate('validate', 'validation');

  const DocumentStage(this.path, this.reprocessName);

  /// Path segment for `POST /imports/{id}/{path}`.
  final String path;

  /// Value accepted by `reprocess`'s `from_stage`, which uses the *noun* form
  /// (`extraction`) where the trigger endpoint uses the verb (`extract`).
  final String reprocessName;

  String get label => switch (this) {
        DocumentStage.preprocess => 'Preparing pages',
        DocumentStage.ocr => 'Reading text',
        DocumentStage.extract => 'Extracting fields',
        DocumentStage.validate => 'Checking totals',
      };
}

/// The result of `POST /exports`.
///
/// Fields match what `service.export` actually returns — `export_batch_id`,
/// `row_count`, `file_format` — plus the `download_url` the router adds. There
/// is no file name in the response: the download endpoint serves the workbook
/// as `<export_batch_id>.xlsx`, which is why the client renames it.
class ExportBatch {
  const ExportBatch({
    required this.exportBatchId,
    this.downloadUrl,
    this.fileFormat,
    this.rowCount = 0,
  });

  final String exportBatchId;
  final String? downloadUrl;
  final String? fileFormat;

  /// Product lines written into the workbook, excluding lines the reviewer
  /// removed from the invoice.
  final int rowCount;

  factory ExportBatch.fromJson(Map<String, dynamic> json) => ExportBatch(
        exportBatchId: json['export_batch_id']?.toString() ?? '',
        downloadUrl: json['download_url']?.toString(),
        fileFormat: json['file_format']?.toString(),
        rowCount: switch (json['row_count']) {
          final int i => i,
          final num n => n.toInt(),
          final String s => int.tryParse(s) ?? 0,
          _ => 0,
        },
      );
}
