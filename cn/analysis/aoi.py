"""Local area-method copy for T5 while models/aoi.py (T3) is unavailable."""

import math


def area_aoi(pairs, start, end, initial_age=0.0):
    """Return (time-average age, maximum age) over [start, end].

    Start with a virtual update generated at start-initial_age. Stale or
    duplicate updates never make the information older. Include the final tail.
    """
    if end <= start or initial_age < 0:
        raise ValueError("AoI needs end > start and initial_age >= 0")
    latest = start - initial_age
    cursor, area, peak = start, 0.0, initial_age
    for generated, received in sorted(pairs, key=lambda pair: pair[1]):
        if not (math.isfinite(generated) and math.isfinite(received)):
            raise ValueError("AoI timestamps must be finite")
        if received < generated:
            raise ValueError("AoI reception precedes generation")
        if received > end:
            break
        if received < start:
            latest = max(latest, generated)
            continue
        age = cursor - latest
        width = received - cursor
        area += age * width + width * width / 2
        peak = max(peak, received - latest)
        latest = max(latest, generated)
        cursor = received
    width = end - cursor
    area += (cursor - latest) * width + width * width / 2
    peak = max(peak, end - latest)
    return area / (end - start), peak
