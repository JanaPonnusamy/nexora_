import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';

/// How one editable field behaves and what it sends.
enum ReviewFieldKind {
  text,
  integer,
  decimal,

  /// Sent as `yyyy-MM-dd`, which is what the server's `date` fields parse.
  date,
}

/// One field in an edit sheet, named by its **wire** key so what the user
/// changes is what gets PATCHed — no translation layer to drift.
class ReviewField {
  const ReviewField({
    required this.name,
    required this.label,
    this.kind = ReviewFieldKind.text,
    this.initial,
    this.hint,
    this.maxLength,
  });

  final String name;
  final String label;
  final ReviewFieldKind kind;

  /// String, num or DateTime — whatever the model holds.
  final Object? initial;

  final String? hint;
  final int? maxLength;
}

/// Edits a small group of fields and returns **only what changed**.
///
/// Partial by design: the server records one audit row per changed field and
/// ignores nulls, so sending the whole object back would either write noise
/// into the audit trail or quietly fail to clear anything. Returns null when
/// the user backs out.
Future<Map<String, dynamic>?> showReviewEditSheet(
  BuildContext context, {
  required String title,
  required List<ReviewField> fields,
  String? note,
}) {
  return showModalBottomSheet<Map<String, dynamic>>(
    context: context,
    backgroundColor: AppColors.surfaceRaised,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => _ReviewEditSheet(title: title, fields: fields, note: note),
  );
}

class _ReviewEditSheet extends StatefulWidget {
  const _ReviewEditSheet({
    required this.title,
    required this.fields,
    this.note,
  });

  final String title;
  final List<ReviewField> fields;
  final String? note;

  @override
  State<_ReviewEditSheet> createState() => _ReviewEditSheetState();
}

class _ReviewEditSheetState extends State<_ReviewEditSheet> {
  final _formKey = GlobalKey<FormState>();
  late final Map<String, TextEditingController> _controllers = {
    for (final field in widget.fields)
      field.name: TextEditingController(text: _initialText(field)),
  };
  late final Map<String, String> _original = {
    for (final field in widget.fields) field.name: _initialText(field),
  };

  @override
  void dispose() {
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  static String _initialText(ReviewField field) => switch (field.initial) {
        null => '',
        final DateTime d => _isoDate(d),
        // 10.0 as "10": a quantity redisplayed with a decimal it never had
        // reads as a value someone changed.
        final num n =>
          n == n.roundToDouble() ? n.toInt().toString() : n.toString(),
        final Object v => v.toString(),
      };

  static String _isoDate(DateTime d) => '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  String? _validate(ReviewField field, String? raw) {
    final value = (raw ?? '').trim();
    if (value.isEmpty) return null;
    return switch (field.kind) {
      ReviewFieldKind.integer =>
        int.tryParse(value) == null ? 'Whole numbers only' : null,
      ReviewFieldKind.decimal =>
        double.tryParse(value) == null ? 'Enter a number' : null,
      // Defensive only: the field is filled by the picker, never typed into.
      ReviewFieldKind.date => DateTime.tryParse(value) == null
          ? 'Pick a date from the calendar'
          : null,
      ReviewFieldKind.text => null,
    };
  }

  Object? _wireValue(ReviewField field, String text) => switch (field.kind) {
        ReviewFieldKind.integer => int.parse(text),
        ReviewFieldKind.decimal => double.parse(text),
        // Already validated as parseable; normalised so a typed date and a
        // picked one send the same string.
        ReviewFieldKind.date => _isoDate(DateTime.parse(text)),
        ReviewFieldKind.text => text,
      };

  void _submit() {
    if (!(_formKey.currentState?.validate() ?? false)) return;

    final patch = <String, dynamic>{};
    for (final field in widget.fields) {
      final text = _controllers[field.name]!.text.trim();
      if (text == _original[field.name]) continue;
      // A blank is "leave it alone", not "clear it": the server drops nulls
      // from a patch, so an empty value could never have cleared the field
      // anyway, and pretending otherwise would look like a save that did
      // nothing.
      if (text.isEmpty) continue;
      patch[field.name] = _wireValue(field, text);
    }
    Navigator.of(context).pop(patch);
  }

  Future<void> _pickDate(ReviewField field) async {
    final controller = _controllers[field.name]!;
    final current = DateTime.tryParse(controller.text.trim());
    final picked = await showDatePicker(
      context: context,
      initialDate: current ?? DateTime.now(),
      // Wide enough for an old invoice being entered late and an expiry years
      // out; narrow enough that a mis-typed year is caught.
      firstDate: DateTime(2000),
      lastDate: DateTime(DateTime.now().year + 15),
    );
    if (picked == null) return;
    setState(() => controller.text = _isoDate(picked));
  }

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);

    return Padding(
      padding: EdgeInsets.only(bottom: media.viewInsets.bottom),
      child: ConstrainedBox(
        // Capped below the full height so the screen behind stays visible — a
        // sheet that fills the display reads as a page, and the reviewer loses
        // the invoice they are correcting against.
        constraints: BoxConstraints(
          maxHeight: (media.size.height - media.viewInsets.bottom) * 0.9,
        ),
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.title,
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    if (widget.note != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(
                          widget.note!,
                          style: const TextStyle(
                            fontSize: 12.5,
                            height: 1.35,
                            color: AppColors.textMuted,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              // The fields scroll; the actions do not. With everything in one
              // scroll view a nine-field line edit put Save below the fold —
              // found by running this on a phone, where `analyze` and the
              // widget tests both let it through.
              Flexible(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      for (final field in widget.fields) ...[
                        _Field(
                          field: field,
                          controller: _controllers[field.name]!,
                          validator: (value) => _validate(field, value),
                          onPickDate: field.kind == ReviewFieldKind.date
                              ? () => _pickDate(field)
                              : null,
                          onSubmitted: _submit,
                        ),
                        const SizedBox(height: 14),
                      ],
                    ],
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 4, 20, 20),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: TextButton(
                            onPressed: () => Navigator.of(context).pop(),
                            style: TextButton.styleFrom(
                              minimumSize: const Size(0, 46),
                            ),
                            child: const Text('Cancel'),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: FilledButton(
                            onPressed: _submit,
                            style: FilledButton.styleFrom(
                              minimumSize: const Size(0, 46),
                            ),
                            child: const Text('Save'),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'A field left blank keeps the value that is already '
                      'there.',
                      style: TextStyle(
                        fontSize: 11.5,
                        color: AppColors.textMuted,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({
    required this.field,
    required this.controller,
    required this.validator,
    required this.onSubmitted,
    this.onPickDate,
  });

  final ReviewField field;
  final TextEditingController controller;
  final String? Function(String?) validator;
  final VoidCallback onSubmitted;
  final VoidCallback? onPickDate;

  @override
  Widget build(BuildContext context) {
    final numeric = field.kind == ReviewFieldKind.integer ||
        field.kind == ReviewFieldKind.decimal;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          field.label,
          style: const TextStyle(
            fontSize: 12.5,
            fontWeight: FontWeight.w600,
            color: AppColors.textSoft,
          ),
        ),
        const SizedBox(height: 6),
        TextFormField(
          controller: controller,
          validator: validator,
          maxLength: field.maxLength,
          readOnly: onPickDate != null,
          onTap: onPickDate,
          keyboardType: numeric
              ? const TextInputType.numberWithOptions(decimal: true)
              : TextInputType.text,
          inputFormatters: [
            if (field.kind == ReviewFieldKind.integer)
              FilteringTextInputFormatter.allow(RegExp(r'[\d-]')),
            if (field.kind == ReviewFieldKind.decimal)
              FilteringTextInputFormatter.allow(RegExp(r'[\d.-]')),
          ],
          onFieldSubmitted: (_) => onSubmitted(),
          decoration: InputDecoration(
            hintText: field.hint,
            counterText: '',
            suffixIcon: onPickDate == null
                ? null
                : const Icon(Icons.event_rounded, size: 18),
          ),
        ),
      ],
    );
  }
}
