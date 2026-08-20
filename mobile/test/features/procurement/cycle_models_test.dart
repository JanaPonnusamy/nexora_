import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/features/procurement/domain/cycle_models.dart';

/// Shaped from a real `GET /api/procurement/cycles` response, not from the
/// router signature — the live row carries nullable end counters and an
/// `active_refresh_id` that decide what the console offers.
Map<String, dynamic> _liveRow({
  String status = 'ACTIVE',
  String? activeRefreshId = '05fc9e95-81b9-4909-abcf-40f8d4d9a602',
  String? endGrn,
  String? endBill,
}) =>
    {
      'cycle_id': '962750b1-b44b-4ff3-9c6c-8eec3b62f340',
      'tenant_id': 'a7eb45bd-bdd7-4ee6-bd7b-61d1c7f4305d',
      'store_id': 'd55f8a0d-c230-44ea-bf56-02f143b948bd',
      'name': 'NMS - 2026-08-10 - Cycle',
      'description': null,
      'status': status,
      'start_grn_number': '11856',
      'start_sale_bill_number': '168777',
      'end_grn_number': endGrn,
      'end_sale_bill_number': endBill,
      'active_refresh_id': activeRefreshId,
      'created_at': '2026-08-10T14:17:36.703000',
      'updated_at': '2026-08-10T14:17:52.680000',
    };

void main() {
  group('ProcurementCycle', () {
    test('parses a live row', () {
      final cycle = ProcurementCycle.fromJson(_liveRow());

      expect(cycle.cycleId, '962750b1-b44b-4ff3-9c6c-8eec3b62f340');
      expect(cycle.name, 'NMS - 2026-08-10 - Cycle');
      expect(cycle.status, CycleStatus.active);
      expect(cycle.startGrnNumber, '11856');
      expect(cycle.hasActiveRefresh, isTrue);
      expect(cycle.createdAt, DateTime.parse('2026-08-10T14:17:36.703000'));
    });

    test('unstamped counters stay null, never zero', () {
      final cycle = ProcurementCycle.fromJson(_liveRow());

      // A 0 here would render as a genuine counter reading.
      expect(cycle.endGrnNumber, isNull);
      expect(cycle.endSaleBillNumber, isNull);
      expect(cycle.isReconciled, isFalse);
    });

    test('a cycle with both end counters is reconciled', () {
      final cycle = ProcurementCycle.fromJson(
        _liveRow(endGrn: '11999', endBill: '169500'),
      );

      expect(cycle.isReconciled, isTrue);
    });

    test('no active refresh is the state "Start refresh" is offered from', () {
      final cycle = ProcurementCycle.fromJson(_liveRow(activeRefreshId: null));

      expect(cycle.hasActiveRefresh, isFalse);
    });

    test(
      'an unrecognised status is carried through rather than collapsed — a '
      'state this build has not heard of is information, not an error',
      () {
        final cycle =
            ProcurementCycle.fromJson(_liveRow(status: 'RECONCILING'));

        expect(cycle.status, CycleStatus.unknown);
        expect(cycle.rawStatus, 'RECONCILING');
      },
    );

    test('an empty string is treated as absent', () {
      final cycle = ProcurementCycle.fromJson({
        ..._liveRow(),
        'start_grn_number': '   ',
        'description': '',
      });

      expect(cycle.startGrnNumber, isNull);
      expect(cycle.description, isNull);
    });

    test('a row missing everything does not throw', () {
      final cycle = ProcurementCycle.fromJson(const {});

      expect(cycle.cycleId, '');
      expect(cycle.name, 'Untitled cycle');
      expect(cycle.status, CycleStatus.unknown);
    });
  });

  group('CyclePage', () {
    test('parses the envelope and knows when more remain', () {
      final page = CyclePage.fromJson({
        'items': [_liveRow(), _liveRow()],
        'total': 10,
        'page': 1,
        'page_size': 2,
      });

      expect(page.items, hasLength(2));
      expect(page.total, 10);
      expect(page.hasMore, isTrue);
    });

    test('the last page reports no more', () {
      final page = CyclePage.fromJson({
        'items': [_liveRow()],
        'total': 3,
        'page': 3,
        'page_size': 1,
      });

      expect(page.hasMore, isFalse);
    });

    test('an empty response is a page, not a failure', () {
      final page = CyclePage.fromJson(const {});

      expect(page.items, isEmpty);
      expect(page.total, 0);
      expect(page.hasMore, isFalse);
    });
  });

  group('CloseOutcome', () {
    test(
      'pending_confirm is a question, not a failure — the console has to be '
      'able to tell it apart from an error or it forces past a check',
      () {
        final outcome = CloseOutcome.fromJson({
          'status': 'pending_confirm',
          'pending_count': 4,
        });

        expect(outcome.needsConfirmation, isTrue);
        expect(outcome.closed, isFalse);
        expect(outcome.pendingCount, 4);
      },
    );

    test('a normal close reads as closed', () {
      final outcome = CloseOutcome.fromJson({'status': 'closed'});

      expect(outcome.closed, isTrue);
      expect(outcome.needsConfirmation, isFalse);
    });

    test('a response with no status is treated as closed', () {
      // The close endpoints return varied envelopes; defaulting to "closed"
      // matches the server, which only names a status when it needs something.
      expect(CloseOutcome.fromJson(const {}).closed, isTrue);
    });
  });
}
