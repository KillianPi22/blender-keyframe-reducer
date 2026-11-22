"""Adaptive, shared-tangent cubic fitting of sampled transform curves. No bpy.

SPDX-License-Identifier: GPL-3.0-or-later
"""
import bisect
import math
from dataclasses import dataclass

from .core import complete, distance


@dataclass
class BezierFit:
    indices: tuple
    slopes: tuple
    max_error: float


def significant_extrema(values, tolerance, kind):
    """Keep dominant turns after a reversal exceeds twice the tolerance.

    Track the running peak/trough through small reversals. A tiny ripple at the
    end of a long arc must not lock its first peak and hide the true extreme.
    This selects anchors only; it does not smooth or replace the source data.
    """
    if len(values) < 3 or kind == 'QUATERNION':
        return set()
    result = set()
    threshold = max(2*tolerance, 1e-12)
    for axis in range(len(values[0])):
        low = high = 0
        direction = 0
        for i in range(1, len(values)):
            value = values[i][axis]
            if direction >= 0 and value > values[high][axis]:
                high = i
            if direction <= 0 and value < values[low][axis]:
                low = i
            if direction <= 0 and value-values[low][axis] > threshold:
                if direction < 0:
                    result.add(low)
                direction, high = 1, i
            elif direction >= 0 and values[high][axis]-value > threshold:
                if direction > 0:
                    result.add(high)
                direction, low = -1, i
    return result - {0, len(values)-1}


def _plateau_edges(values):
    """Seed exact hold boundaries; these remain removable, not protected poses."""
    edges, first = set(), None
    for i in range(len(values)):
        flat = i+1 < len(values) and all(abs(a-b) <= 1e-12
                                        for a, b in zip(values[i], values[i+1]))
        if flat and first is None:
            first = i
        if not flat and first is not None:
            if i-first >= 2:
                edges.update((first, i))
            first = None
    return edges


def hermite(a, b, ma, mb, span, u):
    """Cubic with handles at one third of the time interval."""
    u2, u3 = u*u, u*u*u
    return tuple((2*u3-3*u2+1)*x + (-2*u3+3*u2)*y +
                 (u3-2*u2+u)*span*dx + (u3-u2)*span*dy
                 for x, y, dx, dy in zip(a, b, ma, mb))


def _solve(diagonal, off, rhs):
    """Symmetric tridiagonal solve; samples at interval quarter points give rank."""
    diagonal, rhs = diagonal[:], rhs[:]
    for i in range(1, len(diagonal)):
        if diagonal[i-1] <= 1e-20:
            return None
        factor = off[i-1]/diagonal[i-1]
        diagonal[i] -= factor*off[i-1]
        rhs[i] -= factor*rhs[i-1]
    result = [0.0]*len(rhs)
    for i in range(len(rhs)-1, -1, -1):
        if diagonal[i] <= 1e-20:
            return None
        result[i] = (rhs[i] - (off[i]*result[i+1] if i+1 < len(rhs) else 0))/diagonal[i]
    return result


def _fit_slopes_steps(times, values, samples, reference, fixed=None):
    count, axes = len(times), len(values[0])
    diagonal, off = [0.0]*count, [0.0]*(count-1)
    rhs = [[0.0]*count for _ in range(axes)]
    interval = 0
    for sample, (t, point) in enumerate(zip(samples, reference)):
        if sample % 256 == 0:
            yield
        while interval < count-2 and t > times[interval+1]:
            interval += 1
        span = times[interval+1]-times[interval]
        u = (t-times[interval])/span
        u2, u3 = u*u, u*u*u
        b, c = (u3-2*u2+u)*span, (u3-u2)*span
        diagonal[interval] += b*b
        diagonal[interval+1] += c*c
        off[interval] += b*c
        for axis in range(axes):
            residual = point[axis] - ((2*u3-3*u2+1)*values[interval][axis] +
                                      (-2*u3+3*u2)*values[interval+1][axis])
            rhs[axis][interval] += b*residual
            rhs[axis][interval+1] += c*residual
    fitted = []
    for axis in range(axes):
        yield
        secants = [(b[axis]-a[axis])/(tb-ta)
                   for ta, tb, a, b in zip(times, times[1:], values, values[1:])]
        constrained_diagonal, constrained_off, constrained_rhs = diagonal[:], off[:], rhs[axis][:]
        constraints = {}
        for i in range(count):
            if secants[max(0, i-1)]*secants[min(i, count-2)] <= 0:
                # Solve with flat extrema/plateaus, rather than fitting their
                # neighbors against a slope that will subsequently be erased.
                constraints[i] = 0.0
        for i, point in (fixed or {}).items():
            constraints[i] = point[axis]
        for i, slope in constraints.items():
            if i:
                constrained_rhs[i-1] -= constrained_off[i-1]*slope
                constrained_off[i-1] = 0.0
            if i+1 < count:
                constrained_rhs[i+1] -= constrained_off[i]*slope
                constrained_off[i] = 0.0
        for i, slope in constraints.items():
            constrained_diagonal[i], constrained_rhs[i] = 1.0, slope
        slopes = _solve(constrained_diagonal, constrained_off, constrained_rhs)
        if slopes is None:
            return None
        # Shared slopes give continuous velocity. Limit them to avoid adding
        # new component extrema between anchors. Flat spans have flat handles.
        for i in range(count):
            left = secants[max(0, i-1)]
            right = secants[min(i, count-2)]
            if left*right <= 0 or slopes[i]*left <= 0:
                bounded = 0.0
            else:
                bounded = math.copysign(min(abs(slopes[i]), 3*abs(left), 3*abs(right)), left)
            if fixed and i in fixed and abs(bounded-slopes[i]) > 1e-12:
                return None
            slopes[i] = bounded
        fitted.append(slopes)
    return tuple(tuple(axis[i] for axis in fitted) for i in range(count))


def _errors(knots, points, slopes, samples, reference, kind):
    interval = 0
    for t, point in zip(samples, reference):
        while interval < len(knots)-2 and t > knots[interval+1]:
            interval += 1
        span = knots[interval+1]-knots[interval]
        estimate = hermite(points[interval], points[interval+1], slopes[interval],
                           slopes[interval+1], span, (t-knots[interval])/span)
        error = distance(estimate, point, kind)
        yield interval, t, error if math.isfinite(error) else math.inf


def _maximum_error_steps(knots, points, slopes, samples, reference, kind, limit=math.inf):
    worst = 0.0
    for sample, (_, _, error) in enumerate(_errors(knots, points, slopes, samples, reference, kind)):
        if sample % 256 == 0:
            yield
        worst = max(worst, error)
        if worst > limit:
            break
    return worst


def _prune_steps(fit, times, values, samples, reference, limit, kind, protected):
    """Remove redundant fitted anchors with bounded, local tangent refits.

    A trial changes at most four old spans. Its outer derivatives are fixed,
    leaving every other span unchanged. Check all original reference samples in
    the changed window, never compare against a previously simplified curve.
    Three sweeps revisit neighbors after deletions; this is not a minimal-knot
    optimizer. The sample budget bounds work on long, noisy mocap runs.
    """
    indices = list(fit.indices)
    slopes = dict(zip(indices, fit.slopes))
    budget = 32*len(samples)
    for _ in range(3):
        positions = {key: i for i, key in enumerate(indices)}
        candidates = sorted((key for key in indices[1:-1] if key not in protected),
                            key=lambda key: (times[indices[positions[key]+1]] -
                                             times[indices[positions[key]-1]], key))
        removed = False
        for key in candidates:
            yield
            i = bisect.bisect_left(indices, key)
            lo, hi = max(0, i-2), min(len(indices)-1, i+2)
            trial = indices[lo:i] + indices[i+1:hi+1]
            knots, points = [times[j] for j in trial], [values[j] for j in trial]
            first, last = bisect.bisect_left(samples, knots[0]), bisect.bisect_right(samples, knots[-1])
            budget -= last-first
            if budget < 0:
                break
            checks, target = samples[first:last], reference[first:last]
            fixed = {}
            if lo:
                fixed[0] = slopes[trial[0]]
            if hi < len(indices)-1:
                fixed[len(trial)-1] = slopes[trial[-1]]
            fitted = yield from _fit_slopes_steps(knots, points, checks, target, fixed)
            if fitted is None:
                continue
            error = yield from _maximum_error_steps(knots, points, fitted, checks, target, kind, limit)
            if error > limit:
                continue
            del indices[i]
            slopes.update(zip(trial, fitted))
            removed = True
        if not removed or budget < 0:
            break
    result_slopes = tuple(slopes[i] for i in indices)
    worst = yield from _maximum_error_steps([times[i] for i in indices],
                [values[i] for i in indices], result_slopes, samples, reference, kind)
    return BezierFit(tuple(indices), result_slopes, worst)


def _consolidate_steps(fit, times, values, samples, reference, limit, kind, protected):
    """Replace pairs of unprotected anchors by one better placed source key.

    Simple deletion cannot escape two poorly placed anchors either side of a
    shoulder. Try representative source times, including the slowest point,
    while keeping original values and fixed outer derivatives. Every accepted
    trial removes a key and meets the original error limit. Work is bounded;
    candidate sampling is deliberately not an exhaustive optimal-knot search.
    """
    indices = list(fit.indices)
    slopes = dict(zip(indices, fit.slopes))
    budget = 48*len(samples)
    for _ in range(2):
        changed, i = False, 1
        while i+2 < len(indices):
            yield
            if indices[i] in protected or indices[i+1] in protected:
                i += 1
                continue
            left, right = indices[i-1], indices[i+2]
            lo, hi = max(0, i-2), min(len(indices)-1, i+3)
            a, b = times[left], times[right]
            candidates = {indices[i], indices[i+1]}
            for fraction in (.125, .25, .375, .5, .625, .75, .875):
                pos = bisect.bisect_left(times, a+(b-a)*fraction, left+1, right)
                candidates.add(min(right-1, pos))
            # A flat-tangent shoulder need not change value direction. It is
            # frequently missed by maximum-position-error splitting alone.
            slowest, speed = left+1, math.inf
            for j in range(left+1, right):
                if j % 256 == 0:
                    yield
                velocity = distance(values[j-1], values[j+1], kind)/(times[j+1]-times[j-1])
                if velocity < speed:
                    slowest, speed = j, velocity
            candidates.update(range(max(left+1, slowest-2), min(right, slowest+3)))
            best = None
            first = bisect.bisect_left(samples, times[indices[lo]])
            last = bisect.bisect_right(samples, times[indices[hi]])
            checks, target = samples[first:last], reference[first:last]
            for candidate in sorted(candidates):
                budget -= last-first
                if budget < 0:
                    break
                trial = indices[lo:i] + [candidate] + indices[i+2:hi+1]
                knots, points = [times[j] for j in trial], [values[j] for j in trial]
                fixed = {}
                if lo:
                    fixed[0] = slopes[trial[0]]
                if hi < len(indices)-1:
                    fixed[len(trial)-1] = slopes[trial[-1]]
                fitted = yield from _fit_slopes_steps(knots, points, checks, target, fixed)
                if fitted is None:
                    continue
                worst = yield from _maximum_error_steps(knots, points, fitted, checks, target, kind, limit)
                if worst <= limit and (best is None or worst < best[0]):
                    best = worst, candidate, trial, fitted
            if best is not None:
                _, candidate, trial, fitted = best
                indices[i:i+2] = [candidate]
                slopes.update(zip(trial, fitted))
                changed = True
            if budget < 0:
                break
            i += 1
        if not changed or budget < 0:
            break
    result_slopes = tuple(slopes[i] for i in indices)
    worst = yield from _maximum_error_steps([times[i] for i in indices],
                [values[i] for i in indices], result_slopes, samples, reference, kind)
    return BezierFit(tuple(indices), result_slopes, worst)


def fit_bezier(times, values, samples, reference, tolerance, kind, protected=()):
    return complete(fit_bezier_steps(times, values, samples, reference, tolerance, kind, protected))


def fit_bezier_steps(times, values, samples, reference, tolerance, kind, protected=()):
    """Fit editable cubics, adding source key times only where error demands it.

    Endpoint values and protected times are exact. Slopes are fitted jointly,
    so a surviving key controls both adjoining curves with one tangent direction.
    Validation uses the caller's samples and quaternion orientation when needed;
    this is not a continuous or world-space error guarantee.
    """
    if len(times) < 3:
        return None
    keep = {0, len(times)-1} | set(protected) | _plateau_edges(values)
    # Leave room for Blender's float storage and cubic evaluation.
    limit = max(0.0, tolerance)*0.98
    for _ in range(64):
        ordered = tuple(sorted(keep))
        if len(ordered) >= len(times):
            return None
        knots = [times[i] for i in ordered]
        points = [values[i] for i in ordered]
        slopes = yield from _fit_slopes_steps(knots, points, samples, reference)
        if slopes is None:
            return None
        worst, failing = 0.0, {}
        for sample, (interval, t, error) in enumerate(_errors(knots, points, slopes, samples, reference, kind)):
            if sample % 256 == 0:
                yield
            worst = max(worst, error)
            if error > limit and (interval not in failing or error > failing[interval][1]):
                failing[interval] = t, error
        if not failing:
            args = times, values, samples, reference, limit, kind, set(protected)
            fit = yield from _prune_steps(BezierFit(ordered, slopes, worst), *args)
            fit = yield from _consolidate_steps(fit, *args)
            return (yield from _prune_steps(fit, *args))
        additions = set()
        for interval, (t, _) in failing.items():
            lo, hi = ordered[interval], ordered[interval+1]
            if hi <= lo+1:
                # A joint tangent can be constrained by the adjacent span.
                lo, hi = max(0, lo-2), min(len(times)-1, hi+2)
            candidates = [i for i in range(lo+1, hi) if i not in keep]
            if candidates:
                pos = bisect.bisect_left(times, t, lo+1, hi)
                additions.add(min(candidates, key=lambda i: (abs(times[i]-t), abs(i-pos), i)))
        if not additions:
            return None
        keep |= additions
    return None
