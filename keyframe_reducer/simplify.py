"""Selected-curve simplification retaining source interpolation and tangents.

SPDX-License-Identifier: GPL-3.0-or-later
"""
import bisect
import math

from .core import complete, distance, extrema_indices, reduce_indices
from .fitting import fit_bezier, fit_bezier_steps, significant_extrema
from .engine import (group_tolerance, restore, restore_exact, restore_exact_steps,
                     sample_grid, snapshot, snapshot_steps)
from .selection import selected_runs


def manual_tangent(key):
    return key['interpolation'] == 'BEZIER' and any(
        key[name] in {'FREE', 'ALIGNED'} for name in ('handle_left_type', 'handle_right_type'))


def write_simplified(curves, originals, times, keep):
    """Delete keys, solve automatic interior tangents, freeze the outside.

    Surviving values, times, interpolation and manual handles come from the
    source. Boundary handle types become FREE so later Blender updates cannot
    pull their outward tangents into the selected span.
    """
    start, end = times[0], times[-1]
    retained = {times[i] for i in keep}
    for fc, keys in zip(curves, originals):
        merged = [key for key in keys if not start < key['co'][0] < end or key['co'][0] in retained]
        restore(fc, merged)
        for key, saved in zip(fc.keyframe_points, merged):
            t = saved['co'][0]
            if t <= start or t >= end or manual_tangent(saved):
                if t in (start, end):
                    key.handle_left_type = key.handle_right_type = 'FREE'
                key.handle_left = saved['left']
                key.handle_right = saved['right']


def write_fitted(curves, originals, times, fit):
    return complete(write_fitted_steps(curves, originals, times, fit))


def write_fitted_steps(curves, originals, times, fit):
    """Write editable aligned interior handles and preserve exact outside data."""
    start, end = times[0], times[-1]
    retained_times = [times[i] for i in fit.indices]
    for axis, (fc, source) in enumerate(zip(curves, originals)):
        lookup = {key['co'][0]: key for key in source}
        fitted = []
        for j, t in enumerate(retained_times):
            if j % 128 == 0:
                yield
            key = dict(lookup[t])
            value = key['co'][1]
            left = (t-retained_times[j-1])/3 if j else 0
            right = (retained_times[j+1]-t)/3 if j+1 < len(retained_times) else 0
            slope = fit.slopes[j][axis]
            key['handle_left_type'] = key['handle_right_type'] = 'ALIGNED'
            key['left'] = (t-left, value-left*slope)
            key['right'] = (t+right, value+right*slope)
            key['interpolation'] = 'BEZIER'
            if j == 0:
                key['left'] = lookup[t]['left']
                key['handle_left_type'] = key['handle_right_type'] = 'FREE'
            if j == len(retained_times)-1:
                key['right'] = lookup[t]['right']
                key['handle_left_type'] = key['handle_right_type'] = 'FREE'
                key['interpolation'] = lookup[t]['interpolation']
            fitted.append(key)
        merged = [key for key in source if key['co'][0] < start] + fitted + [
            key for key in source if key['co'][0] > end]
        yield from restore_exact_steps(fc, merged)


def _sample_steps(curves, times):
    points = []
    for index, t in enumerate(times):
        if index % 128 == 0:
            yield
        points.append(tuple(fc.evaluate(t) for fc in curves))
    return points


def _curve_errors_steps(curves, checks, reference, kind):
    errors = []
    for index, (t, point) in enumerate(zip(checks, reference)):
        if index % 128 == 0:
            yield
        errors.append(distance(tuple(fc.evaluate(t) for fc in curves), point, kind))
    return errors


def simplify_window(curves, kind, settings, times):
    return complete(simplify_window_steps(curves, kind, settings, times))


def simplify_window_steps(curves, kind, settings, times):
    originals = []
    for fc in curves:
        originals.append((yield from snapshot_steps(fc)))
    start, end = times[0], times[-1]
    if any(k['interpolation'] not in {'BEZIER', 'LINEAR'} for keys in originals
           for k in keys if start <= k['co'][0] < end):
        return 0, 0.0, 'Constant or special interpolation was preserved.'
    values = yield from _sample_steps(curves, times)
    checks = sample_grid(times, settings.sample_step)
    # Quarter points catch handle-driven features even in subframe intervals
    # shorter than the regular validation step.
    checks = sorted(set(checks) | {a + (b-a)*f for a, b in zip(times, times[1:])
                                  for f in (0.25, 0.5, 0.75)})
    reference = yield from _sample_steps(curves, checks)
    if any(not math.isfinite(v) for point in reference for v in point):
        return 0, 0.0, 'Non-finite values were preserved.'
    if kind == 'QUATERNION' and (
            any(sum(v*v for v in point) < 1e-10 for point in reference) or
            any(sum(x*y for x, y in zip(a, b)) <= 0 for a, b in zip(values, values[1:]))):
        return 0, 0.0, 'Quaternion sign discontinuity was preserved.'
    tolerance = group_tolerance(kind, settings)
    refit = settings.simplify_mode == 'FIT'
    extrema = significant_extrema if refit else extrema_indices
    protected = extrema(values, tolerance, kind) if settings.preserve_extrema else set()
    manual_times = {k['co'][0] for keys in originals for k in keys if manual_tangent(k)}
    protected_times = {k['co'][0] for keys in originals for k in keys
                       if settings.preserve_marked and k['type'] in {'EXTREME', 'BREAKDOWN'}}
    if settings.preserve_manual and not refit:
        protected_times |= manual_times
    protected |= {i for i, t in enumerate(times) if t in protected_times}
    if refit:
        # Validate between the fitting samples too. If a narrow error peak was
        # missed, fit once more against the finer immutable reference. Common
        # curves avoid paying for the larger least-squares solve on every trial.
        validation = sorted(set(checks) | {a+(b-a)*f/8 for a, b in zip(times, times[1:])
                                          for f in (1, 3, 5, 7)})
        truth = yield from _sample_steps(curves, validation)
        if any(not math.isfinite(v) for point in truth for v in point):
            return 0, 0.0, 'Non-finite values were preserved.'
        for fit_checks, fit_reference in ((checks, reference), (validation, truth)):
            fit = yield from fit_bezier_steps(times, values, fit_checks, fit_reference, tolerance, kind, protected)
            if fit is None:
                return 0, 0.0, 'No simpler editable Bezier fit met the tolerance; source keys were preserved.'
            yield from write_fitted_steps(curves, originals, times, fit)
            errors = yield from _curve_errors_steps(curves, validation, truth, kind)
            if all(math.isfinite(e) for e in errors) and max(errors, default=0.0) <= tolerance*(1+1e-5):
                return (len(times)-len(fit.indices))*len(curves), max(errors, default=0.0), ''
            for fc, keys in zip(curves, originals):
                yield from restore_exact_steps(fc, keys)
        return 0, 0.0, 'Bezier validation exceeded the tolerance; source keys were preserved.'
    if settings.preserve_manual and all(t in manual_times for t in times[1:-1]):
        return 0, 0.0, 'Manual tangent keys were protected; disable Protect Manual Tangents to allow removal.'
    keep = reduce_indices(times, values, tolerance, kind, protected)
    for _ in range(64):
        if len(keep) >= len(times):
            break
        write_simplified(curves, originals, times, keep)
        errors = [distance(tuple(fc.evaluate(t) for fc in curves), point, kind)
                  for t, point in zip(checks, reference)]
        worst = max(errors, default=0.0) if all(math.isfinite(e) for e in errors) else math.inf
        if math.isfinite(worst) and worst <= tolerance * (1 + 1e-5):
            return (len(times)-len(keep))*len(curves), worst, ''
        ordered = sorted(keep)
        retained_times = [times[i] for i in ordered]
        # Refine every failing interval, using the largest error in that
        # interval. Each candidate is rebuilt from the immutable snapshot.
        failing = {}
        for t, error in zip(checks, errors):
            if math.isfinite(error) and error <= tolerance:
                continue
            pos = min(len(ordered)-1, max(1, bisect.bisect_right(retained_times, t)))
            lo, hi = ordered[pos-1], ordered[pos]
            if hi <= lo+1:
                lo, hi = max(0, lo-2), min(len(times)-1, hi+2)
            interval = lo, hi
            if interval not in failing or error > failing[interval][1]:
                failing[interval] = t, error
        additions = set()
        for (lo, hi), (t, _) in failing.items():
            candidates = [i for i in range(lo, hi+1) if i not in keep]
            if candidates:
                additions.add(min(candidates, key=lambda i: abs(times[i]-t)))
        if not additions:
            break
        keep |= additions
    for fc, keys in zip(curves, originals):
        restore_exact(fc, keys)
    return 0, 0.0, ''


def simplify_selected_group(curves, kind, settings, selection):
    return complete(simplify_selected_group_steps(curves, kind, settings, selection))


def simplify_selected_group_steps(curves, kind, settings, selection):
    before = sum(len(fc.keyframe_points) for fc in curves)
    active = [fc for fc in curves if selection.get((fc.data_path, fc.array_index))]
    if not active:
        return before, before, 0.0, ''
    if kind == 'QUATERNION' and [fc.array_index for fc in active] != [0, 1, 2, 3]:
        return before, before, 0.0, 'Quaternion selection: select W, X, Y and Z keys together.'
    if any(fc.hide or fc.lock or fc.mute or fc.modifiers or fc.sampled_points for fc in active):
        return before, before, 0.0, 'Hidden, locked, muted, modified or sampled curves were preserved.'
    runs = selected_runs(active, selection)
    if not runs:
        return before, before, 0.0, 'Selection: at least 3 consecutive keys must be selected on all participating channels.'
    removed, error, warnings = 0, 0.0, set()
    for times in runs:
        if len(times) > 20000:
            raise ValueError('Selection too long: limit of 20,000 keys per run.')
        count, measured, warning = yield from simplify_window_steps(active, kind, settings, times)
        removed += count
        error = max(error, measured)
        if warning:
            warnings.add(warning)
    return before, before-removed, error, ' '.join(sorted(warnings))
