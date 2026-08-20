"""Compact passcode algorithm — ported verbatim from the legacy PassGen tool.

The store software parses these codes character-by-character, so the layout and
the checksum must not change:

    StoreCode(2) OrderNo(1) MinDays(2) MaxDays(2) OrdY(1) CmpY(1) DD(2) MM(2) Chk(1)

Min/Max days are Base36 in 2 characters, which is what bounds them to 0..1295 —
there is no policy limit on top of that.
"""

BASE36_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

#: Largest value a 2-character Base36 field can carry ("ZZ").
MAX_BASE36_2 = 36 * 36 - 1


def int_to_base36(n):
    """Convert an integer to a 2-character Base36 string, zero padded."""
    if n == 0:
        return '00'

    digits = []
    temp_n = n
    while temp_n > 0:
        temp_n, rem = divmod(temp_n, 36)
        digits.append(BASE36_CHARS[rem])

    return ''.join(reversed(digits)).rjust(2, '0')


def calculate_checksum(code13):
    """Single Base36 character: sum of ASCII values of the 13-char body mod 36."""
    total = sum(ord(c) for c in code13)
    return BASE36_CHARS[total % 36]


def generate_compact_passcode(store_code, order_no, min_days, max_days, ordy, cmpy, input_date):
    """Build the 14-character passcode for one store / one day-range."""
    store_str = str(store_code).zfill(2)
    order_str = str(order_no)
    min36 = int_to_base36(min_days)
    max36 = int_to_base36(max_days)
    ordy_str = str(ordy)
    cmpy_str = str(cmpy)
    day_str = str(input_date.day).zfill(2)
    month_str = str(input_date.month).zfill(2)

    code13 = store_str + order_str + min36 + max36 + ordy_str + cmpy_str + day_str + month_str
    return code13 + calculate_checksum(code13)
