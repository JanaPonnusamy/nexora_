import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/document_extraction/application/document_export_controller.dart';
import 'package:nexora_mobile/features/document_extraction/application/document_review_controller.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_review.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/document_page_view.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/review_edit_sheet.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/review_header_card.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/review_item_card.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/review_summary_card.dart';

/// Check what the pipeline read, fix what it got wrong, commit the invoice.
///
/// This is the step the whole capture flow exists to reach: OCR produces a
/// plausible invoice, and a person who can see both the paper and the numbers
/// decides whether it is right. Everything here is organised around that —
/// what is wrong first, the source image one tap away, and every field the
/// server will accept a correction for editable in place.
class DocumentReviewScreen extends ConsumerStatefulWidget {
  const DocumentReviewScreen({
    super.key,
    required this.importId,
    this.batchId,
  });

  final int importId;

  /// The local queue row this import came from, when it was opened from the
  /// queue. Carried so a save can move that row off "Ready to review".
  final int? batchId;

  @override
  ConsumerState<DocumentReviewScreen> createState() =>
      _DocumentReviewScreenState();
}

class _DocumentReviewScreenState extends ConsumerState<DocumentReviewScreen> {
  bool _busy = false;
  bool _onlyFlagged = false;

  DocumentReviewController get _controller =>
      ref.read(documentReviewControllerProvider);

  /// True when an action is already running, in which case it says so.
  ///
  /// Checked before a sheet opens rather than only before it submits: letting
  /// someone retype a line and then dropping the edit silently is worse than
  /// asking them to wait a second.
  bool get _stillSaving {
    if (!_busy) return false;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('The last change is still saving.')),
    );
    return true;
  }

  /// Runs one action, reporting what it did. Actions are serialised: two
  /// concurrent patches against the same import would race the re-validation
  /// that follows each one, and the second answer would win at random.
  Future<ReviewActionResult?> _run(
    Future<ReviewActionResult> Function() action,
  ) async {
    if (_busy) return null;
    setState(() => _busy = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final result = await action();
      if (!result.blockedByErrors) {
        messenger.showSnackBar(
          SnackBar(
            content: Text(result.message),
            backgroundColor: result.ok ? null : AppColors.dangerSunk,
          ),
        );
      }
      return result;
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _editDetails(DocumentReview review) async {
    if (_stillSaving) return;
    final header = review.header;
    final patch = await showReviewEditSheet(
      context,
      title: 'Invoice details',
      fields: [
        ReviewField(
          name: 'invoice_number',
          label: 'Invoice number',
          initial: header.invoiceNumber,
          maxLength: 50,
        ),
        ReviewField(
          name: 'invoice_date',
          label: 'Invoice date',
          kind: ReviewFieldKind.date,
          initial: header.invoiceDate,
        ),
        ReviewField(
          name: 'invoice_type',
          label: 'Type',
          initial: header.invoiceType,
          hint: 'Purchase, return, …',
          maxLength: 30,
        ),
        ReviewField(
          name: 'order_number',
          label: 'Order number',
          initial: header.orderNumber,
          maxLength: 50,
        ),
        ReviewField(
          name: 'transport',
          label: 'Transport / delivery',
          initial: header.transport,
          maxLength: 100,
        ),
        ReviewField(
          name: 'salesman',
          label: 'Salesman',
          initial: header.salesman,
          maxLength: 100,
        ),
        ReviewField(
          name: 'credit_days',
          label: 'Credit days',
          kind: ReviewFieldKind.integer,
          initial: header.creditDays,
        ),
      ],
    );
    if (patch == null || patch.isEmpty || !mounted) return;
    await _run(() => _controller.patchHeader(review.importId, patch));
  }

  Future<void> _editAmounts(DocumentReview review) async {
    if (_stillSaving) return;
    final header = review.header;
    final patch = await showReviewEditSheet(
      context,
      title: 'Amounts',
      note: 'The net amount is what the invoice is posted for — it is worth '
          'checking against the paper even when the lines add up.',
      fields: [
        ReviewField(
          name: 'gross_amount',
          label: 'Gross',
          kind: ReviewFieldKind.decimal,
          initial: header.grossAmount,
        ),
        ReviewField(
          name: 'discount_amount',
          label: 'Discount',
          kind: ReviewFieldKind.decimal,
          initial: header.discountAmount,
        ),
        ReviewField(
          name: 'scheme_discount',
          label: 'Scheme discount',
          kind: ReviewFieldKind.decimal,
          initial: header.schemeDiscount,
        ),
        ReviewField(
          name: 'cash_discount',
          label: 'Cash discount',
          kind: ReviewFieldKind.decimal,
          initial: header.cashDiscount,
        ),
        ReviewField(
          name: 'taxable_amount',
          label: 'Taxable',
          kind: ReviewFieldKind.decimal,
          initial: header.taxableAmount,
        ),
        ReviewField(
          name: 'cgst_amount',
          label: 'CGST',
          kind: ReviewFieldKind.decimal,
          initial: header.cgstAmount,
        ),
        ReviewField(
          name: 'sgst_amount',
          label: 'SGST',
          kind: ReviewFieldKind.decimal,
          initial: header.sgstAmount,
        ),
        ReviewField(
          name: 'igst_amount',
          label: 'IGST',
          kind: ReviewFieldKind.decimal,
          initial: header.igstAmount,
        ),
        ReviewField(
          name: 'cess_amount',
          label: 'CESS',
          kind: ReviewFieldKind.decimal,
          initial: header.cessAmount,
        ),
        ReviewField(
          name: 'round_off',
          label: 'Round off',
          kind: ReviewFieldKind.decimal,
          initial: header.roundOff,
        ),
        ReviewField(
          name: 'net_amount',
          label: 'Net amount',
          kind: ReviewFieldKind.decimal,
          initial: header.netAmount,
        ),
      ],
    );
    if (patch == null || patch.isEmpty || !mounted) return;
    await _run(() => _controller.patchHeader(review.importId, patch));
  }

  Future<void> _assignSupplier(DocumentReview review) async {
    if (_stillSaving) return;
    final supplier = review.supplier;
    final patch = await showReviewEditSheet(
      context,
      title: supplier.isUnknown ? 'Assign a supplier' : 'Change the supplier',
      note: 'A GST or DL number is what matches this invoice to a supplier '
          'record; the name alone is a weaker match.',
      fields: [
        ReviewField(
          name: 'supplier_name',
          label: 'Supplier name',
          initial: supplier.supplierName,
          maxLength: 200,
        ),
        ReviewField(
          name: 'matched_supplier_code',
          label: 'Supplier code',
          initial: supplier.matchedSupplierCode,
          maxLength: 50,
        ),
        ReviewField(
          name: 'gst_number',
          label: 'GST number',
          initial: supplier.gstNumber,
          maxLength: 20,
        ),
        ReviewField(
          name: 'dl_number',
          label: 'DL number',
          initial: supplier.dlNumber,
          maxLength: 50,
        ),
      ],
    );
    if (patch == null || patch.isEmpty || !mounted) return;
    await _run(() => _controller.assignSupplier(review.importId, patch));
  }

  Future<void> _editItem(DocumentReview review, DocumentItem item) async {
    if (_stillSaving) return;
    final patch = await showReviewEditSheet(
      context,
      title: 'Line ${item.lineNumber}',
      fields: [
        ReviewField(
          name: 'normalized_product_name',
          label: 'Product',
          initial: item.productName,
          maxLength: 300,
        ),
        ReviewField(
          name: 'pack',
          label: 'Packing',
          initial: item.pack,
          maxLength: 50,
        ),
        ReviewField(
          name: 'hsn_code',
          label: 'HSN code',
          initial: item.hsnCode,
          maxLength: 20,
        ),
        ReviewField(
          name: 'batch_number',
          label: 'Batch',
          initial: item.batchNumber,
          maxLength: 50,
        ),
        ReviewField(
          name: 'expiry_date',
          label: 'Expiry',
          kind: ReviewFieldKind.date,
          initial: item.expiryDate,
          hint: item.expiryRaw == null
              ? null
              // The unparsed text is the reviewer's best clue about what the
              // date should be, so it belongs next to the field, not in a
              // finding they have to scroll back to.
              : 'Read from the invoice as "${item.expiryRaw}"',
        ),
        ReviewField(
          name: 'quantity',
          label: 'Quantity',
          kind: ReviewFieldKind.decimal,
          initial: item.quantity,
        ),
        ReviewField(
          name: 'free_quantity',
          label: 'Free quantity',
          kind: ReviewFieldKind.decimal,
          initial: item.freeQuantity,
        ),
        ReviewField(
          name: 'purchase_rate',
          label: 'Purchase rate',
          kind: ReviewFieldKind.decimal,
          initial: item.purchaseRate,
        ),
        ReviewField(
          name: 'ptr',
          label: 'PTR',
          kind: ReviewFieldKind.decimal,
          initial: item.ptr,
        ),
        ReviewField(
          name: 'mrp',
          label: 'MRP',
          kind: ReviewFieldKind.decimal,
          initial: item.mrp,
        ),
        ReviewField(
          name: 'gst_percent',
          label: 'GST %',
          kind: ReviewFieldKind.decimal,
          initial: item.gstPercent,
        ),
        ReviewField(
          name: 'discount_percent',
          label: 'Purchase discount %',
          kind: ReviewFieldKind.decimal,
          initial: item.discountPercent,
        ),
        ReviewField(
          name: 'discount_amount',
          label: 'Purchase discount amount',
          kind: ReviewFieldKind.decimal,
          initial: item.discountAmount,
        ),
        ReviewField(
          name: 'amount',
          label: 'Line amount',
          kind: ReviewFieldKind.decimal,
          initial: item.amount,
        ),
      ],
    );
    if (patch == null || patch.isEmpty || !mounted) return;
    await _run(
      () => _controller.patchItem(review.importId, item.itemId, patch),
    );
  }

  Future<void> _excludeItem(DocumentReview review, DocumentItem item) async {
    if (_stillSaving) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Remove this line?'),
        content: Text(
          'Line ${item.lineNumber} (${item.displayName}) will not be part of '
          'the invoice or the export.\n\n'
          // The server has no endpoint that puts a line back, so this is the
          // last point at which the decision is reversible.
          'This cannot be undone from the app.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Keep'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: TextButton.styleFrom(foregroundColor: AppColors.danger),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    await _run(() => _controller.excludeItem(review.importId, item.itemId));
  }

  Future<void> _save(DocumentReview review) async {
    final result = await _run(
      () => _controller.save(review.importId, batchId: widget.batchId),
    );
    if (result == null || !mounted) return;

    if (result.blockedByErrors) {
      final force = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Save with errors?'),
          content: Text(
            '${result.message}\n\n'
            'Saving anyway is recorded against your name. Do it only when the '
            'invoice is right and the rule is wrong.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Go back'),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              style: TextButton.styleFrom(foregroundColor: AppColors.warning),
              child: const Text('Save anyway'),
            ),
          ],
        ),
      );
      if (force != true || !mounted) return;
      await _run(
        () => _controller.save(
          review.importId,
          batchId: widget.batchId,
          force: true,
        ),
      );
    }
    // Deliberately stays on the screen rather than popping back to the queue.
    // The moment after saving is when someone wants to send the invoice on,
    // and the bar has just become an Export button — bouncing them out would
    // hide the step they are most likely to want next. Back is one tap.
  }

  Future<void> _export(DocumentReview review) async {
    if (_stillSaving) return;
    setState(() => _busy = true);
    final messenger = ScaffoldMessenger.of(context);
    final origin = _shareOrigin();
    try {
      final outcome =
          await ref.read(documentExportControllerProvider).exportAndShare(
        importIds: [review.importId],
        batchIds: [if (widget.batchId != null) widget.batchId!],
        // The invoice number, not the import id: it is what the person
        // receiving the workbook will recognise.
        fileLabel: review.header.invoiceNumber ?? '${review.importId}',
        subject: 'Invoice ${review.header.invoiceNumber ?? ''} '
                '${review.supplier.supplierName ?? ''}'
            .trim(),
        sharePositionOrigin: origin,
      );
      messenger.showSnackBar(
        SnackBar(
          content: Text(outcome.message),
          backgroundColor: outcome.ok ? null : AppColors.dangerSunk,
        ),
      );
      // The server moved the import to EXPORTED, so re-read rather than
      // leaving the bar claiming it still needs exporting.
      if (outcome.ok) await _controller.refresh(review.importId);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Anchor for the iPad share popover, which throws without one.
  Rect? _shareOrigin() {
    final box = context.findRenderObject();
    if (box is! RenderBox || !box.hasSize) return null;
    return box.localToGlobal(Offset.zero) & box.size;
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(documentReviewProvider(widget.importId));

    return Scaffold(
      appBar: AppBar(
        title: Text('Invoice #${widget.importId}'),
        actions: [
          IconButton(
            tooltip: 'View the captured pages',
            onPressed: () => DocumentPageViewer.open(
              context,
              importId: widget.importId,
              pageCount: async.valueOrNull?.header.pageCount ?? 1,
            ),
            icon: const Icon(Icons.image_outlined),
          ),
        ],
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => _Error(
          message: error is ApiException ? error.message : '$error',
          onRetry: () =>
              ref.invalidate(documentReviewProvider(widget.importId)),
        ),
        data: _content,
      ),
      bottomNavigationBar: async.valueOrNull == null
          ? null
          : _SaveBar(
              review: async.value!,
              busy: _busy,
              onSave: () => _save(async.value!),
              onExport: () => _export(async.value!),
            ),
    );
  }

  /// One definition of "worth a look", shared by the count and the filter so
  /// the chip can never offer to hide lines it did not count.
  static bool _needsLook(DocumentReview review, DocumentItem item) =>
      !item.isExcluded &&
      (item.needsAttention() || review.findingsFor(item.itemId).isNotEmpty);

  Widget _content(DocumentReview review) {
    final readOnly = review.isCommitted;
    final flagged = review.items
        .where((i) => _needsLook(review, i))
        .toList(growable: false);
    final items = _onlyFlagged ? flagged : review.items;

    return RefreshIndicator(
      onRefresh: () => _controller.refresh(review.importId),
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            sliver: SliverList.list(
              children: [
                ReviewSummaryCard(review: review),
                const SizedBox(height: 12),
                ReviewHeaderCard(
                  review: review,
                  readOnly: readOnly,
                  onEditDetails: () => _editDetails(review),
                  onEditAmounts: () => _editAmounts(review),
                  onAssignSupplier: () => _assignSupplier(review),
                ),
                const SizedBox(height: 18),
                _ItemsHeader(
                  lines: review.includedItems.length,
                  flagged: flagged.length,
                  onlyFlagged: _onlyFlagged,
                  onToggleFilter: () =>
                      setState(() => _onlyFlagged = !_onlyFlagged),
                ),
                const SizedBox(height: 10),
              ],
            ),
          ),
          if (items.isEmpty)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(32, 12, 32, 40),
                child: EmptyState(
                  icon: _onlyFlagged
                      ? Icons.check_circle_outline_rounded
                      : Icons.receipt_long_outlined,
                  message: _onlyFlagged
                      ? 'No line needs attention.'
                      : review.status.isProcessing
                          // Not an error: the pipeline can still be running
                          // when someone opens the document early.
                          ? 'The server is still reading this document.\n'
                              'Pull down to check again.'
                          : 'No lines were extracted from this document.',
                ),
              ),
            )
          else
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
              sliver: SliverList.builder(
                itemCount: items.length,
                itemBuilder: (context, index) {
                  final item = items[index];
                  return ReviewItemCard(
                    item: item,
                    findings: review.findingsFor(item.itemId),
                    // Deliberately not disabled while an action is in flight:
                    // buttons that come and go move every card under the
                    // reviewer's thumb. `_stillSaving` explains the wait
                    // instead.
                    readOnly: readOnly,
                    onEdit: () => _editItem(review, item),
                    onExclude: () => _excludeItem(review, item),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}

class _ItemsHeader extends StatelessWidget {
  const _ItemsHeader({
    required this.lines,
    required this.flagged,
    required this.onlyFlagged,
    required this.onToggleFilter,
  });

  final int lines;
  final int flagged;
  final bool onlyFlagged;
  final VoidCallback onToggleFilter;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '$lines line${lines == 1 ? '' : 's'}',
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
              if (flagged > 0)
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(
                    '$flagged need${flagged == 1 ? 's' : ''} a look',
                    style: const TextStyle(
                      fontSize: 11.5,
                      color: AppColors.warningInk,
                    ),
                  ),
                ),
            ],
          ),
        ),
        if (flagged > 0)
          // Only offered when it would do something: a filter that hides
          // nothing teaches people the filter is broken.
          FilterChip(
            selected: onlyFlagged,
            onSelected: (_) => onToggleFilter(),
            label: const Text('Only flagged'),
            labelStyle: const TextStyle(fontSize: 12),
            visualDensity: VisualDensity.compact,
          ),
      ],
    );
  }
}

/// The commit action, always in reach at the bottom rather than at the end of
/// a hundred line items.
class _SaveBar extends StatelessWidget {
  const _SaveBar({
    required this.review,
    required this.busy,
    required this.onSave,
    required this.onExport,
  });

  final DocumentReview review;
  final bool busy;
  final VoidCallback onSave;
  final VoidCallback onExport;

  @override
  Widget build(BuildContext context) {
    if (review.isCommitted) {
      final exported = review.status == DocumentStatus.exported;

      // Export is offered right here rather than only from the queue: the
      // moment after saving is when someone actually wants to send the
      // invoice on, and making them navigate back to find it invites them to
      // forget.
      return _Bar(
        child: Row(
          children: [
            Expanded(
              child: Text(
                exported
                    ? 'Exported. Sharing again builds a fresh workbook.'
                    : 'Saved and ready to export.',
                style: const TextStyle(
                  fontSize: 12,
                  color: AppColors.textMuted,
                ),
              ),
            ),
            const SizedBox(width: 12),
            FilledButton.icon(
              onPressed: busy ? null : onExport,
              icon: busy
                  ? const SizedBox(
                      width: 14,
                      height: 14,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.ios_share_rounded, size: 18),
              label: Text(exported ? 'Share again' : 'Export'),
              style: FilledButton.styleFrom(
                minimumSize: const Size(0, 46),
                padding: const EdgeInsets.symmetric(horizontal: 18),
                backgroundColor: exported ? AppColors.surfaceHover : null,
                foregroundColor: exported ? AppColors.textSoft : null,
              ),
            ),
          ],
        ),
      );
    }

    final blocked = !review.canSave;

    return _Bar(
      child: Row(
        children: [
          Expanded(
            child: Text(
              blocked
                  ? 'Errors have to be resolved, or overridden on save.'
                  : 'Saving commits these values for export.',
              style: const TextStyle(fontSize: 12, color: AppColors.textMuted),
            ),
          ),
          const SizedBox(width: 12),
          FilledButton.icon(
            onPressed: busy ? null : onSave,
            icon: busy
                ? const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.check_rounded, size: 18),
            label: Text(blocked ? 'Save anyway' : 'Save invoice'),
            style: FilledButton.styleFrom(
              // Explicit, because the theme's default forces an infinite width
              // inside a Row.
              minimumSize: const Size(0, 46),
              padding: const EdgeInsets.symmetric(horizontal: 18),
              backgroundColor: blocked ? AppColors.warningSunk : null,
              foregroundColor: blocked ? AppColors.warningInk : null,
            ),
          ),
        ],
      ),
    );
  }
}

class _Bar extends StatelessWidget {
  const _Bar({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border(top: BorderSide(color: AppColors.rule)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
          child: child,
        ),
      ),
    );
  }
}

class _Error extends StatelessWidget {
  const _Error({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: StatusCard(
          accentColor: AppColors.danger,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'This invoice could not be opened',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 4),
              Text(
                message,
                style: const TextStyle(
                  fontSize: 12.5,
                  color: AppColors.textSoft,
                ),
              ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: onRetry,
                style: FilledButton.styleFrom(
                  minimumSize: const Size(0, 40),
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                ),
                child: const Text('Try again'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
