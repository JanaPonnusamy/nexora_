import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';

import 'package:nexora_mobile/core/di/agent_providers.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/pass_gen/data/pass_gen_api.dart';
import 'package:nexora_mobile/features/pass_gen/domain/pass_gen_models.dart';

final passGenApiProvider = Provider<PassGenApi>(
  (ref) => PassGenApi(ref.watch(dioProvider)),
);

/// Stores and their numeric codes. Platform-wide, so no tenant filter is sent.
final passGenStoresProvider =
    FutureProvider.autoDispose<List<PassGenStore>>((ref) {
  return ref.watch(passGenApiProvider).stores();
});

/// Generates the legacy 14-character store passcodes for the field ordering
/// app. Not a gate pass, despite the module name.
///
/// Platform-admin only — the server 403s everyone else, and the More tab hides
/// the entry point for non-platform users so nobody is offered a dead end.
class PassGenScreen extends ConsumerStatefulWidget {
  const PassGenScreen({super.key});

  @override
  ConsumerState<PassGenScreen> createState() => _PassGenScreenState();
}

class _PassGenScreenState extends ConsumerState<PassGenScreen> {
  late PassGenRequest _request = PassGenRequest(
    orderNo: 0,
    targetDate: DateTime.now(),
    minDays: 0,
    maxDays: 30,
  );

  PassGenRowResult? _result;
  String? _error;
  bool _busy = false;

  Future<void> _generate() async {
    final problem = _request.problem;
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }

    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await ref.read(passGenApiProvider).generate(_request);
      if (mounted) setState(() => _result = result);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _request.targetDate,
      // A passcode is minted for an order window around today; a year either
      // side is generous without offering dates the ordering app rejects.
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 1),
    );
    if (picked == null || !mounted) return;
    setState(() => _request = _request.copyWith(targetDate: picked));
  }

  Future<void> _pickStores() async {
    final stores = await ref.read(passGenStoresProvider.future);
    if (!mounted) return;
    final chosen = await showModalBottomSheet<List<String>>(
      context: context,
      backgroundColor: AppColors.surfaceRaised,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _StorePicker(
        stores: stores,
        selected: _request.storeIds,
      ),
    );
    if (chosen == null || !mounted) return;
    setState(() => _request = _request.copyWith(storeIds: chosen));
  }

  void _copy(String passcode) {
    Clipboard.setData(ClipboardData(text: passcode));
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Copied $passcode')),
    );
  }

  Future<void> _shareAll() async {
    final result = _result;
    if (result == null || result.results.isEmpty) return;
    final body =
        result.results.map((r) => '${r.label}: ${r.passcode}').join('\n');
    await Share.share(
      body,
      subject: 'Store passcodes — ${_dateLabel(_request.targetDate)}',
    );
  }

  @override
  Widget build(BuildContext context) {
    final isPlatformUser = ref.watch(isPlatformUserProvider);
    final result = _result;

    if (!isPlatformUser) {
      return Scaffold(
        appBar: AppBar(title: const Text('Pass Gen')),
        body: const Center(
          child: Padding(
            padding: EdgeInsets.all(32),
            child: EmptyState(
              message: 'Pass Gen is restricted to platform administrators.',
              icon: Icons.lock_outline_rounded,
            ),
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Pass Gen'),
        actions: [
          if (result != null && result.results.isNotEmpty)
            IconButton(
              onPressed: _shareAll,
              icon: const Icon(Icons.ios_share_rounded),
              tooltip: 'Share all',
            ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
        children: [
          _settingsCard(),
          if (_error != null) ...[
            const SizedBox(height: 12),
            _errorCard(),
          ],
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: _busy ? null : _generate,
              icon: _busy
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(Icons.password_rounded, size: 20),
              label: Text(_busy ? 'Generating…' : 'Generate passcodes'),
            ),
          ),
          if (result != null) ...[
            const SizedBox(height: 20),
            SectionHeader(
              title: 'PASSCODES (${result.results.length})',
              icon: Icons.key_rounded,
            ),
            if (result.results.isEmpty)
              const EmptyState(
                message: 'No passcodes were produced.',
                icon: Icons.key_off_rounded,
              )
            else
              for (final r in result.results)
                _PasscodeCard(result: r, onCopy: () => _copy(r.passcode)),
            if (result.skipped.isNotEmpty) ...[
              const SizedBox(height: 12),
              _skippedCard(result.skipped),
            ],
          ],
        ],
      ),
    );
  }

  Widget _settingsCard() {
    return StatusCard(
      accentColor: AppColors.accent,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'ORDER NO',
            style: TextStyle(
              fontSize: 10.5,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.4,
              color: AppColors.textMuted,
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            children: [
              for (var n = 0; n <= PassGenRequest.maxOrderNo; n++)
                ChoiceChip(
                  label: Text('$n'),
                  selected: _request.orderNo == n,
                  onSelected: (_) =>
                      setState(() => _request = _request.copyWith(orderNo: n)),
                ),
            ],
          ),
          const Divider(height: 24),
          Row(
            children: [
              const Expanded(
                child: Text(
                  'Target date',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                ),
              ),
              TextButton.icon(
                onPressed: _pickDate,
                icon: const Icon(Icons.calendar_today_rounded, size: 16),
                label: Text(_dateLabel(_request.targetDate)),
                style: TextButton.styleFrom(
                  minimumSize: const Size(0, 36),
                  padding: const EdgeInsets.symmetric(horizontal: 10),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ),
            ],
          ),
          const Divider(height: 24),
          const Text(
            'DAY WINDOW',
            style: TextStyle(
              fontSize: 10.5,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.4,
              color: AppColors.textMuted,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: _NumberField(
                  label: 'Min days',
                  value: _request.minDays,
                  onChanged: (v) =>
                      setState(() => _request = _request.copyWith(minDays: v)),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _NumberField(
                  label: 'Max days',
                  value: _request.maxDays,
                  onChanged: (v) =>
                      setState(() => _request = _request.copyWith(maxDays: v)),
                ),
              ),
            ],
          ),
          const Divider(height: 24),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            title: const Text('Order Yes', style: TextStyle(fontSize: 13.5)),
            value: _request.orderYes,
            onChanged: (v) =>
                setState(() => _request = _request.copyWith(orderYes: v)),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            title: const Text(
              'Compare last order',
              style: TextStyle(fontSize: 13.5),
            ),
            value: _request.compareLastOrder,
            onChanged: (v) => setState(
              () => _request = _request.copyWith(compareLastOrder: v),
            ),
          ),
          const Divider(height: 24),
          Row(
            children: [
              Expanded(
                child: Text(
                  _request.storeIds.isEmpty
                      ? 'All mapped stores'
                      : '${_request.storeIds.length} store'
                          '${_request.storeIds.length == 1 ? '' : 's'} selected',
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              TextButton.icon(
                onPressed: _pickStores,
                icon: const Icon(Icons.storefront_outlined, size: 16),
                label: const Text('Choose'),
                style: TextButton.styleFrom(
                  minimumSize: const Size(0, 36),
                  padding: const EdgeInsets.symmetric(horizontal: 10),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _errorCard() {
    return StatusCard(
      accentColor: AppColors.danger,
      child: Row(
        children: [
          const Icon(
            Icons.error_outline_rounded,
            size: 18,
            color: AppColors.dangerInk,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              _error!,
              style: const TextStyle(fontSize: 12.5, color: AppColors.text),
            ),
          ),
        ],
      ),
    );
  }

  /// Unmapped stores are named, not silently dropped: seven passcodes from ten
  /// selected stores otherwise looks like a failure with no explanation.
  Widget _skippedCard(List<String> skipped) {
    return StatusCard(
      accentColor: AppColors.warning,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${skipped.length} store${skipped.length == 1 ? '' : 's'} skipped',
            style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 4),
          const Text(
            'These have no numeric store code, so no passcode can be built '
            'for them. Set one in the store picker.',
            style: TextStyle(fontSize: 12, color: AppColors.textSoft),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final code in skipped)
                InfoChip(label: code, color: AppColors.warning),
            ],
          ),
        ],
      ),
    );
  }

  static String _dateLabel(DateTime d) => '${d.day.toString().padLeft(2, '0')}/'
      '${d.month.toString().padLeft(2, '0')}/${d.year}';
}

class _NumberField extends StatefulWidget {
  const _NumberField({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final int value;
  final ValueChanged<int> onChanged;

  @override
  State<_NumberField> createState() => _NumberFieldState();
}

class _NumberFieldState extends State<_NumberField> {
  late final _controller = TextEditingController(text: '${widget.value}');

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: _controller,
      keyboardType: TextInputType.number,
      inputFormatters: [
        FilteringTextInputFormatter.digitsOnly,
        // Four digits covers the 1295 ceiling without letting a typo become a
        // request the server rejects with a 422.
        LengthLimitingTextInputFormatter(4),
      ],
      decoration: InputDecoration(labelText: widget.label),
      onChanged: (v) => widget.onChanged(int.tryParse(v) ?? 0),
    );
  }
}

class _PasscodeCard extends StatelessWidget {
  const _PasscodeCard({required this.result, required this.onCopy});

  final PassGenResult result;
  final VoidCallback onCopy;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: onCopy,
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.rule),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        result.label,
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        result.passcode,
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 1.5,
                          // Monospaced digits so a 14-character code can be
                          // read aloud or transcribed without losing place.
                          fontFeatures: [FontFeature.tabularFigures()],
                          color: AppColors.accentInk,
                        ),
                      ),
                    ],
                  ),
                ),
                const Icon(
                  Icons.copy_rounded,
                  size: 18,
                  color: AppColors.textMuted,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Multi-select over the platform's stores, with inline mapping for the
/// unmapped ones so a skipped store can be fixed without leaving the flow.
class _StorePicker extends ConsumerStatefulWidget {
  const _StorePicker({required this.stores, required this.selected});

  final List<PassGenStore> stores;
  final List<String> selected;

  @override
  ConsumerState<_StorePicker> createState() => _StorePickerState();
}

class _StorePickerState extends ConsumerState<_StorePicker> {
  final Set<String> _selected = {};
  late List<PassGenStore> _stores = widget.stores;

  @override
  void initState() {
    super.initState();
    _selected.addAll(widget.selected);
  }

  Future<void> _setCode(PassGenStore store) async {
    final controller = TextEditingController(
      text: store.numericCode?.toString() ?? '',
    );
    final code = await showDialog<int?>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Store code for ${store.label}'),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: TextInputType.number,
          inputFormatters: [
            FilteringTextInputFormatter.digitsOnly,
            LengthLimitingTextInputFormatter(2),
          ],
          decoration: const InputDecoration(
            labelText: 'Numeric code (0–99)',
            helperText: 'The two-digit store field inside the passcode.',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(
              int.tryParse(controller.text) ?? -1,
            ),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (code == null || code < 0 || code > 99 || !mounted) return;

    final messenger = ScaffoldMessenger.of(context);
    try {
      // The endpoint returns the whole list, so the local copy is replaced
      // rather than patched — no chance of drifting from the server.
      final updated =
          await ref.read(passGenApiProvider).setStoreCode(store.storeId, code);
      if (mounted) setState(() => _stores = updated);
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.75,
      maxChildSize: 0.92,
      builder: (context, controller) => Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 4, 12, 8),
            child: Row(
              children: [
                const Expanded(
                  child: Text(
                    'Stores',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                TextButton(
                  onPressed: () => setState(_selected.clear),
                  style: TextButton.styleFrom(
                    minimumSize: const Size(0, 36),
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  child: const Text('All stores'),
                ),
                TextButton(
                  onPressed: () =>
                      Navigator.of(context).pop(_selected.toList()),
                  style: TextButton.styleFrom(
                    minimumSize: const Size(0, 36),
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  child: const Text('Done'),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: ListView.builder(
              controller: controller,
              itemCount: _stores.length,
              itemBuilder: (context, i) {
                final store = _stores[i];
                return CheckboxListTile(
                  value: _selected.contains(store.storeId),
                  onChanged: store.isMapped
                      ? (checked) => setState(() {
                            if (checked == true) {
                              _selected.add(store.storeId);
                            } else {
                              _selected.remove(store.storeId);
                            }
                          })
                      : null,
                  title: Text(
                    store.label,
                    style: const TextStyle(fontSize: 14),
                  ),
                  subtitle: Text(
                    store.isMapped
                        ? '${store.storeCode} · code ${store.numericCode}'
                        : '${store.storeCode} · not mapped',
                    style: TextStyle(
                      fontSize: 11.5,
                      color: store.isMapped
                          ? AppColors.textMuted
                          : AppColors.warningInk,
                    ),
                  ),
                  secondary: IconButton(
                    onPressed: () => _setCode(store),
                    icon: Icon(
                      store.isMapped
                          ? Icons.edit_outlined
                          : Icons.add_circle_outline_rounded,
                      size: 18,
                      color: store.isMapped
                          ? AppColors.textMuted
                          : AppColors.warning,
                    ),
                    tooltip: store.isMapped ? 'Change code' : 'Set code',
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
