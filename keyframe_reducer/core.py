"""Numerical helpers for Keyframe Reducer. No Blender dependencies.

SPDX-License-Identifier: GPL-3.0-or-later
"""
import math


def distance(a, b, kind):
    if kind == 'QUATERNION':
        na = math.sqrt(sum(v*v for v in a))
        nb = math.sqrt(sum(v*v for v in b))
        if na < 1e-10 or nb < 1e-10:
            return float('inf')
        dot = abs(sum(x*y for x, y in zip(a, b)) / (na*nb))
        return 2.0 * math.acos(min(1.0, max(0.0, dot)))
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def interpolate(a, b, factor):
    return tuple(x + (y-x)*factor for x, y in zip(a, b))


def reduce_indices(times, values, tolerance, kind, protected=()):
    """RDP with vertical/vector error, never geometric frame/value distance.

    Quaternion error is angular, while interpolation matches Blender's
    component F-curves. Euler values remain unwrapped (full spins preserved).
    """
    count = len(times)
    if count <= 2:
        return set(range(count))
    keep = {0, count - 1} | set(protected)
    anchors = sorted(keep)
    pending = list(zip(anchors, anchors[1:]))
    threshold = max(tolerance, 1e-9)
    while pending:
        first, last = pending.pop()
        if last <= first + 1:
            continue
        span = times[last] - times[first]
        worst, split = threshold, None
        for i in range(first+1, last):
            estimate = interpolate(values[first], values[last], (times[i]-times[first])/span)
            error = distance(estimate, values[i], kind)
            if error > worst:
                worst, split = error, i
        if split is not None:
            keep.add(split)
            pending.extend(((first, split), (split, last)))
    return keep


def extrema_indices(values, tolerance, kind):
    """Protect significant component turning points, not every noise peak."""
    if len(values) < 3:
        return set()
    # Quaternion component extrema have no angular unit equivalence.
    # Their essential orientation changes are protected by angular error instead.
    if kind == 'QUATERNION':
        return set()
    result = set()
    for axis in range(len(values[0])):
        previous = 0
        direction = 0
        for i in range(1, len(values)):
            delta = values[i][axis] - values[i-1][axis]
            sign = 1 if delta > 1e-12 else -1 if delta < -1e-12 else 0
            if sign and direction and sign != direction:
                peak = i-1
                if abs(values[peak][axis]-values[previous][axis]) > tolerance*2:
                    result.add(peak)
                previous = peak
            if sign:
                direction = sign
    return result
