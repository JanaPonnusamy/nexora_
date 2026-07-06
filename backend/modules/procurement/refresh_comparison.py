"""Next-Refresh comparison rules (pure Python, no I/O) — Sprint 3, Module 4.

When Refresh N+1 is created, the previous Refresh's pending remaining must
influence the new suggestion automatically, and products already completely
received must not reappear.
"""


def adjust_suggested(engine_suggested, previous_remaining, carried,
                     previously_completed):
    """Return (include, new_suggested) for a product in the next Refresh.

    * previously_completed with nothing fresh to buy -> excluded (won't reappear)
    * carried pending (undelivered) is re-procured on top of the fresh baseline
    """
    engine_suggested = engine_suggested or 0
    previous_remaining = previous_remaining or 0

    if previously_completed and engine_suggested <= 0:
        return False, 0

    new_suggested = engine_suggested
    if carried:
        new_suggested += previous_remaining

    return new_suggested > 0, new_suggested
