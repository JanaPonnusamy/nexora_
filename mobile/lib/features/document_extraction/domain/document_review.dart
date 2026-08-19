/// Models for the review payload (`GET /imports/{id}/review`).
///
/// The server returns wide, sparse rows straight out of `doc_import` /
/// `doc_import_item`, and OCR legitimately fails to find fields — so almost
/// everything here is nullable and parsing is defensive. A malformed row must
/// degrade to a blank field for the user to correct, never crash the review.
library;

import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';

double? _asDouble(Object? v) => switch (v) {
      final num n => n.toDouble(),
      final String s => double.tryParse(s),
      _ => null,
    };

int? _asInt(Object? v) => switch (v) {
      final int i => i,
      final num n => n.toInt(),
      final String s => int.tryParse(s),
      _ => null,
    };

bool _asBool(Object? v) => switch (v) {
      final bool b => b,
      final num n => n != 0,
      final String s => s.toLowerCase() == 'true' || s == '1',
      _ => false,
    };

DateTime? _asDate(Object? v) =>
    v is String && v.isNotEmpty ? DateTime.tryParse(v) : null;

String? _asString(Object? v) {
  if (v == null) return null;
  final s = v.toString().trim();
  return s.isEmpty ? null : s;
}

/// Supplier detection result. The pipeline runs a GST → DL → phone → name
/// priority chain; a miss sets [isUnknown] rather than failing the import.
class DocumentSupplier {
  const DocumentSupplier({
    this.matchedSupplierCode,
    this.supplierName,
    this.gstNumber,
    this.dlNumber,
    this.matchMethod,
    this.matchConfidence,
    this.isUnknown = false,
  });

  final String? matchedSupplierCode;
  final String? supplierName;
  final String? gstNumber;
  final String? dlNumber;
  final String? matchMethod;
  final double? matchConfidence;
  final bool isUnknown;

  factory DocumentSupplier.fromJson(Map<String, dynamic> json) =>
      DocumentSupplier(
        matchedSupplierCode: _asString(json['matched_supplier_code']),
        supplierName: _asString(json['supplier_name']),
        gstNumber: _asString(json['gst_number']),
        dlNumber: _asString(json['dl_number']),
        matchMethod: _asString(json['supplier_match_method']),
        matchConfidence: _asDouble(json['supplier_match_confidence']),
        isUnknown: _asBool(json['is_supplier_unknown']),
      );
}

/// Invoice header. Field names match `HeaderPatch` on the server so an edit
/// round-trips without translation.
class DocumentHeader {
  const DocumentHeader({
    required this.importId,
    this.invoiceNumber,
    this.invoiceDate,
    this.invoiceType,
    this.orderNumber,
    this.supplierName,
    this.gstNumber,
    this.dlNumber,
    this.grossAmount,
    this.discountAmount,
    this.taxableAmount,
    this.cgstAmount,
    this.sgstAmount,
    this.igstAmount,
    this.roundOff,
    this.netAmount,
    this.itemCount,
    this.totalQuantity,
    this.ocrConfidence,
    this.pageCount,
    this.isDuplicate = false,
    this.failureReason,
  });

  final int importId;
  final String? invoiceNumber;
  final DateTime? invoiceDate;
  final String? invoiceType;
  final String? orderNumber;
  final String? supplierName;
  final String? gstNumber;
  final String? dlNumber;
  final double? grossAmount;
  final double? discountAmount;
  final double? taxableAmount;
  final double? cgstAmount;
  final double? sgstAmount;
  final double? igstAmount;
  final double? roundOff;
  final double? netAmount;
  final int? itemCount;
  final double? totalQuantity;
  final double? ocrConfidence;
  final int? pageCount;
  final bool isDuplicate;
  final String? failureReason;

  factory DocumentHeader.fromJson(Map<String, dynamic> json) => DocumentHeader(
        importId: _asInt(json['import_id']) ?? 0,
        invoiceNumber: _asString(json['invoice_number']),
        invoiceDate: _asDate(json['invoice_date']),
        invoiceType: _asString(json['invoice_type']),
        orderNumber: _asString(json['order_number']),
        supplierName: _asString(json['supplier_name']),
        gstNumber: _asString(json['gst_number']),
        dlNumber: _asString(json['dl_number']),
        grossAmount: _asDouble(json['gross_amount']),
        discountAmount: _asDouble(json['discount_amount']),
        taxableAmount: _asDouble(json['taxable_amount']),
        cgstAmount: _asDouble(json['cgst_amount']),
        sgstAmount: _asDouble(json['sgst_amount']),
        igstAmount: _asDouble(json['igst_amount']),
        roundOff: _asDouble(json['round_off']),
        netAmount: _asDouble(json['net_amount']),
        itemCount: _asInt(json['item_count']),
        totalQuantity: _asDouble(json['total_quantity']),
        ocrConfidence: _asDouble(json['ocr_confidence']),
        pageCount: _asInt(json['page_count']),
        isDuplicate: _asBool(json['is_duplicate']),
        failureReason: _asString(json['failure_reason']),
      );
}

/// One extracted line item. [confidence] drives the low-confidence highlight
/// that tells a reviewer where to look first.
class DocumentItem {
  const DocumentItem({
    required this.itemId,
    required this.lineNumber,
    this.productCode,
    this.productName,
    this.pack,
    this.hsnCode,
    this.batchNumber,
    this.expiryRaw,
    this.expiryDate,
    this.quantity,
    this.freeQuantity,
    this.ptr,
    this.purchaseRate,
    this.mrp,
    this.gstPercent,
    this.discountPercent,
    this.discountAmount,
    this.amount,
    this.confidence,
    this.isExcluded = false,
  });

  final int itemId;
  final int lineNumber;
  final String? productCode;
  final String? productName;
  final String? pack;
  final String? hsnCode;
  final String? batchNumber;
  final String? expiryRaw;
  final DateTime? expiryDate;
  final double? quantity;
  final double? freeQuantity;
  final double? ptr;
  final double? purchaseRate;
  final double? mrp;
  final double? gstPercent;
  final double? discountPercent;
  final double? discountAmount;
  final double? amount;
  final double? confidence;
  final bool isExcluded;

  /// Below this the row is visually flagged for review. The pipeline persists
  /// uncertain rows rather than dropping them, so surfacing them is the whole
  /// point of the review step.
  static const double lowConfidenceThreshold = 0.75;

  bool get isLowConfidence =>
      confidence != null && confidence! < lowConfidenceThreshold;

  /// The name to show: the normalised form when the pipeline produced one,
  /// otherwise the raw OCR text.
  String get displayName => productName ?? '(unnamed line $lineNumber)';

  /// No ProductCode means the line cannot post to inventory, whatever else is
  /// right about it.
  bool get isMissingProduct => productCode == null;

  /// A real batch is alphanumeric and at least two characters. The common OCR
  /// failure is noise — `--`, `.`, a single stray glyph — not a wrong but
  /// plausible value.
  bool get hasInvalidBatch {
    final batch = (batchNumber ?? '').trim();
    return batch.length < 2 || !RegExp('[A-Za-z0-9]').hasMatch(batch);
  }

  /// True when the expiry could not be parsed at all, or parsed to a date that
  /// has already passed. [now] is a parameter so the check is testable without
  /// a fake clock.
  bool hasExpiryProblem([DateTime? now]) {
    final date = expiryDate;
    // Expired stock on an incoming invoice is unusual enough to put in front of
    // a person, not unusual enough to reject on its own.
    if (date != null) return date.isBefore(now ?? DateTime.now());
    // An `expiry_raw` that never became a date means OCR read something the
    // parser could not use ("13/25"), which is exactly what review is for.
    return expiryRaw != null;
  }

  /// Short reasons this line is worth a second look, in the same words the web
  /// console uses (`frontend/src/components/document-extraction/
  /// reviewChecks.ts`) so a line flagged at the counter is the same line
  /// flagged at head office.
  List<String> highlights([DateTime? now]) => [
        if (isMissingProduct) 'Missing product',
        if (isLowConfidence) 'Low confidence',
        if (hasInvalidBatch) 'Invalid batch',
        if (hasExpiryProblem(now)) 'Invalid expiry',
      ];

  bool needsAttention([DateTime? now]) => highlights(now).isNotEmpty;

  factory DocumentItem.fromJson(Map<String, dynamic> json) => DocumentItem(
        itemId: _asInt(json['item_id']) ?? 0,
        lineNumber: _asInt(json['line_number']) ?? 0,
        productCode: _asString(json['product_code']),
        productName: _asString(json['normalized_product_name']) ??
            _asString(json['ocr_product_name']),
        pack: _asString(json['pack']),
        hsnCode: _asString(json['hsn_code']),
        batchNumber: _asString(json['batch_number']),
        expiryRaw: _asString(json['expiry_raw']),
        expiryDate: _asDate(json['expiry_date']),
        quantity: _asDouble(json['quantity']),
        freeQuantity: _asDouble(json['free_quantity']),
        ptr: _asDouble(json['ptr']),
        purchaseRate: _asDouble(json['purchase_rate']),
        mrp: _asDouble(json['mrp']),
        gstPercent: _asDouble(json['gst_percent']),
        discountPercent: _asDouble(json['discount_percent']),
        discountAmount: _asDouble(json['discount_amount']),
        amount: _asDouble(json['amount']),
        confidence: _asDouble(json['confidence']),
        isExcluded: _asBool(json['is_excluded']),
      );
}

/// One rule outcome from the validation stage.
class ValidationFinding {
  const ValidationFinding({
    required this.severity,
    required this.message,
    this.field,
    this.rule,
    this.itemId,
    this.expected,
    this.actual,
  });

  final ValidationStatus severity;
  final String message;
  final String? field;
  final String? rule;

  /// Set when the finding is about one line rather than the invoice as a
  /// whole, so the review screen can put it on that line's card instead of in
  /// a list the user then has to match up by hand.
  final int? itemId;

  final String? expected;
  final String? actual;

  bool get isError => severity == ValidationStatus.failed;

  factory ValidationFinding.fromJson(Map<String, dynamic> json) =>
      ValidationFinding(
        severity: ValidationStatus.fromWire(
          _asString(json['severity']) ?? _asString(json['status']),
        ),
        message: _asString(json['message']) ??
            _asString(json['detail']) ??
            'Unspecified finding',
        field: _asString(json['field']),
        // The server's key is `rule_code`; `rule` is accepted too so a finding
        // from an older payload still names its rule.
        rule: _asString(json['rule_code']) ?? _asString(json['rule']),
        itemId: _asInt(json['item_id']),
        expected: _asString(json['expected_value']),
        actual: _asString(json['actual_value']),
      );
}

/// One "does this invoice add up?" comparison: what the header claims against
/// what the lines actually sum to.
///
/// Independent of the server's per-field findings — those check that a field is
/// present and parseable, this checks that the document is internally
/// consistent, which is the question a person asks before trusting it.
class ReconcileCheck {
  const ReconcileCheck({
    required this.label,
    required this.extracted,
    required this.computed,
    this.exact = false,
    this.money = true,
  });

  final String label;

  /// The header's own figure. Only comparable checks are built, so this is
  /// never null.
  final double extracted;

  /// The same figure derived from the included lines.
  final double computed;

  /// True for counts, where being one out is a real difference rather than
  /// rounding. Money and quantity carry [tolerance]; a line count does not.
  final bool exact;

  /// False for the checks that count things. "3 lines" written as "3.00" reads
  /// as a currency amount, which is exactly the confusion this card exists to
  /// prevent.
  final bool money;

  /// Money never matches to the paisa after OCR and rounding; anything within
  /// a rupee counts as balanced rather than a mismatch worth a red flag.
  static const double tolerance = 1;

  double get difference => computed - extracted;

  bool get balanced => exact ? difference == 0 : difference.abs() <= tolerance;
}

/// Everything the review screen needs, from one `GET .../review` call.
class DocumentReview {
  const DocumentReview({
    required this.importId,
    required this.status,
    required this.header,
    required this.supplier,
    required this.items,
    this.validationStatus = ValidationStatus.pending,
    this.findings = const [],
    this.previewImagePath,
  });

  final int importId;
  final DocumentStatus status;
  final DocumentHeader header;
  final DocumentSupplier supplier;
  final List<DocumentItem> items;
  final ValidationStatus validationStatus;
  final List<ValidationFinding> findings;

  /// Server-side path of the preprocessed page image. Only its presence
  /// matters to the client — the bytes are fetched from the authenticated
  /// preview endpoint, not from this path.
  final String? previewImagePath;

  /// Excluded rows stay in the payload (the server keeps them) but are not
  /// part of the invoice.
  List<DocumentItem> get includedItems =>
      items.where((i) => !i.isExcluded).toList(growable: false);

  int get lowConfidenceCount =>
      includedItems.where((i) => i.isLowConfidence).length;

  /// Included lines with anything worth a second look on them.
  int flaggedCount([DateTime? now]) =>
      includedItems.where((i) => i.needsAttention(now)).length;

  /// Sum of included line amounts — compared against the header's net amount
  /// as the reviewer's main sanity check.
  double get itemsTotal =>
      includedItems.fold(0, (sum, i) => sum + (i.amount ?? 0));

  double get itemsQuantity =>
      includedItems.fold(0, (sum, i) => sum + (i.quantity ?? 0));

  /// Findings about the invoice as a whole, i.e. not attached to one line.
  List<ValidationFinding> get headerFindings =>
      findings.where((f) => f.itemId == null).toList(growable: false);

  List<ValidationFinding> findingsFor(int itemId) =>
      findings.where((f) => f.itemId == itemId).toList(growable: false);

  int get errorCount => findings.where((f) => f.isError).length;

  int get warningCount =>
      findings.where((f) => f.severity == ValidationStatus.warning).length;

  /// The three internal-consistency checks, built only where the header
  /// actually carries a figure to compare against. A missing header total is
  /// already reported as a server finding, so showing it here as a mismatch
  /// would say the same thing twice in different words.
  List<ReconcileCheck> get reconciliation => [
        if (header.netAmount != null)
          ReconcileCheck(
            label: 'Net amount',
            extracted: header.netAmount!,
            computed: itemsTotal,
          ),
        if (header.totalQuantity != null)
          ReconcileCheck(
            label: 'Total quantity',
            extracted: header.totalQuantity!,
            computed: itemsQuantity,
            money: false,
          ),
        if (header.itemCount != null)
          ReconcileCheck(
            label: 'Line count',
            extracted: header.itemCount!.toDouble(),
            computed: includedItems.length.toDouble(),
            exact: true,
            money: false,
          ),
      ];

  bool get reconciles => reconciliation.every((c) => c.balanced);

  bool get canSave => !validationStatus.blocksSave;

  /// Committed — saved, and possibly already written into a workbook.
  /// Either way the values are no longer the reviewer's to change here.
  bool get isCommitted => status.isCommitted;

  static List<T> _list<T>(
    Object? raw,
    T Function(Map<String, dynamic>) parse,
  ) {
    if (raw is! List) return const [];
    return raw
        .whereType<Map<String, dynamic>>()
        .map(parse)
        .toList(growable: false);
  }

  factory DocumentReview.fromJson(Map<String, dynamic> json) {
    final headerJson = json['header'];
    final header = DocumentHeader.fromJson(
      headerJson is Map<String, dynamic> ? headerJson : const {},
    );
    final supplierJson = json['supplier'];
    final validation = json['validation'];

    // `validation` is either the findings array or an object wrapping it.
    Object? findingsRaw;
    ValidationStatus status = ValidationStatus.pending;
    if (validation is Map<String, dynamic>) {
      findingsRaw = validation['findings'] ?? validation['items'];
      status = ValidationStatus.fromWire(
        _asString(validation['validation_status']) ??
            _asString(validation['status']),
      );
    } else if (validation is List) {
      findingsRaw = validation;
    }

    return DocumentReview(
      importId: _asInt(json['import_id']) ?? header.importId,
      status: DocumentStatus.fromWire(_asString(json['status'])),
      header: header,
      supplier: DocumentSupplier.fromJson(
        supplierJson is Map<String, dynamic> ? supplierJson : const {},
      ),
      items: _list(json['items'], DocumentItem.fromJson),
      validationStatus: status,
      findings: _list(findingsRaw, ValidationFinding.fromJson),
      previewImagePath: _asString(json['preview_image_path']) ??
          _asString(headerJson is Map<String, dynamic>
              ? headerJson['preview_image_path']
              : null),
    );
  }
}
