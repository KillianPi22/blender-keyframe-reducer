"""Strict key-selection reduction: disjoint runs, exact outside preservation.

SPDX-License-Identifier: GPL-3.0-or-later
"""
import bisect
import math
from .core import distance, reduce_indices, extrema_indices
from .engine import (snapshot, restore_exact, sample_grid, group_tolerance,
                     write_group)


def selected_runs(curves, selection):
    """An unselected key on any participating channel breaks the run.

    Channels that have no selected keys are not participating (except for a
    quaternion, which is checked by the caller). Never enlarge to a min/max
    range spanning holes in the selection, and never manufacture key times.
    """
    times = sorted({float(k.co.x) for fc in curves for k in fc.keyframe_points})
    masks = [selection.get((fc.data_path, fc.array_index), set()) for fc in curves]
    key_times = [{float(k.co.x) for k in fc.keyframe_points} for fc in curves]
    runs, current = [], []
    for t in times:
        if all(t in mask and t in existing for mask, existing in zip(masks, key_times)):
            current.append(t)
        else:
            if len(current) >= 3:
                runs.append(current)
            current = []
    if len(current) >= 3:
        runs.append(current)
    return runs


def write_window(curves, times, values, keep, originals, interpolation):
    start, end = times[0], times[-1]
    segments = [[k for k in keys if start <= k['co'][0] <= end] for keys in originals]
    write_group(curves, times, values, keep, segments, interpolation)
    for fc, source in zip(curves, originals):
        reduced = snapshot(fc)
        lookup = {k['co'][0]: k for k in source}
        for key in reduced:
            original = lookup[key['co'][0]]
            for name in ('type','select_control_point','select_left_handle','select_right_handle'):
                key[name] = original[name]
        # Preserve the outgoing segment before/after the selected window.
        first, last = reduced[0], reduced[-1]
        first['left'] = lookup[start]['left']
        first['handle_left_type'] = first['handle_right_type'] = 'FREE'
        last['right'] = lookup[end]['right']
        last['handle_left_type'] = last['handle_right_type'] = 'FREE'
        for name in ('interpolation', 'easing', 'amplitude', 'back', 'period'):
            last[name] = lookup[end][name]
        merged = ([k for k in source if k['co'][0] < start] + reduced +
                  [k for k in source if k['co'][0] > end])
        restore_exact(fc, merged)


def reduce_window(curves, kind, settings, times):
    originals = [snapshot(fc) for fc in curves]
    start, end = times[0], times[-1]
    before = sum(len(keys) for keys in originals)
    # The last key's interpolation belongs to the *outside* segment.
    if any(k['interpolation'] not in {'BEZIER','LINEAR'} for keys in originals
           for k in keys if start <= k['co'][0] < end):
        return 0, 0.0
    values = [tuple(fc.evaluate(t) for fc in curves) for t in times]
    if any(not math.isfinite(v) for point in values for v in point):
        return 0, 0.0
    if kind == 'QUATERNION' and (any(sum(v*v for v in point)<1e-10 for point in values) or
            any(sum(x*y for x,y in zip(a,b))<=0 for a,b in zip(values,values[1:]))):
        return 0, 0.0
    tolerance = group_tolerance(kind, settings)
    protected = extrema_indices(values, tolerance, kind) if settings.preserve_extrema else set()
    if settings.preserve_marked:
        marked = {k['co'][0] for keys in originals for k in keys if k['type'] in {'EXTREME','BREAKDOWN'}}
        protected |= {i for i,t in enumerate(times) if t in marked}
    keep = reduce_indices(times, values, tolerance, kind, protected)
    checks = sample_grid(times, settings.sample_step)
    reference = [tuple(fc.evaluate(t) for fc in curves) for t in checks]
    for _ in range(64):
        if len(keep) >= len(times):
            break
        write_window(curves, times, values, keep, originals, settings.interpolation)
        errors = [distance(tuple(fc.evaluate(t) for fc in curves),v,kind)
                  for t,v in zip(checks,reference)]
        worst = max(errors, default=0.0)
        if worst <= tolerance*(1+1e-5):
            # Selection is strict: assert every outside key, including handles,
            # type and selection flags, survived exactly as stored.
            outside_unchanged = all(
                [k for k in snapshot(fc) if k['co'][0]<start or k['co'][0]>end] ==
                [k for k in source if k['co'][0]<start or k['co'][0]>end]
                for fc,source in zip(curves,originals))
            if outside_unchanged:
                after = sum(len(fc.keyframe_points) for fc in curves)
                return before-after, worst
            break
        retained = sorted(keep)
        retained_times = [times[i] for i in retained]
        additions = set()
        for t, error in zip(checks,errors):
            if error <= tolerance:
                continue
            pos = bisect.bisect_right(retained_times,t)
            lo, hi = retained[max(0,pos-1)], retained[min(pos,len(retained)-1)]
            if hi <= lo+1:
                lo,hi = max(0,lo-2),min(len(times)-1,hi+2)
            options = [i for i in range(lo,hi+1) if i not in keep]
            if options:
                additions.add(min(options,key=lambda i:abs(times[i]-t)))
        if not additions:
            break
        keep |= additions
    for fc,source in zip(curves,originals):
        restore_exact(fc,source)
    return 0,0.0


def reduce_selected_group(curves, kind, settings, selection):
    before = sum(len(fc.keyframe_points) for fc in curves)
    active = [fc for fc in curves if selection.get((fc.data_path,fc.array_index))]
    if not active:
        return before,before,0.0,''
    if kind == 'QUATERNION' and [fc.array_index for fc in active] != [0,1,2,3]:
        return before,before,0.0,'Quaternion selection: select W, X, Y and Z keys together.'
    if any(fc.lock or fc.mute or fc.modifiers or fc.sampled_points for fc in active):
        return before,before,0.0,'Locked, muted or modified curves were preserved.'
    runs = selected_runs(active, selection)
    if not runs:
        return before,before,0.0,'Selection: at least 3 consecutive keys must be selected on all participating channels.'
    removed,max_error = 0,0.0
    for times in runs:
        if len(times)>20000:
            raise ValueError('Selection too long: limit of 20,000 keys per run.')
        count,error = reduce_window(active,kind,settings,times)
        removed += count
        max_error = max(max_error,error)
    return before,before-removed,max_error,''
