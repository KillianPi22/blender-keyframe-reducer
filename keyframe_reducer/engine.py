"""Blender Action-slot aware, error-checked grouped key reduction.

SPDX-License-Identifier: GPL-3.0-or-later
"""
import bisect
import math
import re
from dataclasses import dataclass, field
from .core import complete, distance, reduce_indices, extrema_indices


TRANSFORMS = {'location': 'LOCATION', 'rotation_euler': 'EULER',
              'rotation_quaternion': 'QUATERNION', 'scale': 'SCALE'}
BONE_PATH = re.compile(r'^pose\.bones\[("(?:[^"\\]|\\.)*")\]')
KEY_FIELDS = ('interpolation', 'easing', 'type', 'handle_left_type',
              'handle_right_type', 'amplitude', 'back', 'period',
              'select_control_point', 'select_left_handle', 'select_right_handle')


@dataclass
class Settings:
    strength: float = 1.0
    position_error: float = 0.1
    rotation_error: float = math.radians(0.5)
    scale_error: float = 0.001
    interpolation: str = 'BEZIER'
    preserve_extrema: bool = True
    preserve_marked: bool = True
    sample_step: float = 0.5
    selected_bones: set | None = None
    key_selection: list | None = None
    method: str = 'REDUCE'
    preserve_manual: bool = True
    simplify_mode: str = 'KEEP'


@dataclass
class Report:
    before: int = 0
    after: int = 0
    reduced_groups: int = 0
    preserved_groups: int = 0
    max_error_ratio: float = 0.0
    max_position_error: float = 0.0
    max_rotation_error: float = 0.0
    max_scale_error: float = 0.0
    warnings: list = field(default_factory=list)
    scope_before: int = 0
    scope_after: int = 0
    curve_details: list = field(default_factory=list)


def slot_curves(action, slot):
    """Only the active slot; never touch other subjects in a shared Action."""
    if slot is None:
        raise ValueError('Choose the armature slot in the Action Editor.')
    bags = [bag for layer in action.layers for strip in layer.strips
            for bag in getattr(strip, 'channelbags', ()) if bag.slot_handle == slot.handle]
    if len(bags) != 1:
        raise ValueError('This Action must have exactly one channelbag for the active slot.')
    return list(bags[0].fcurves)


def find_slot(action, identifier):
    return next((s for s in action.slots if s.identifier == identifier), None)


def snapshot(fc):
    return complete(snapshot_steps(fc))


def snapshot_steps(fc):
    result = []
    for index, k in enumerate(fc.keyframe_points):
        if index % 128 == 0:
            yield
        result.append(dict(co=tuple(k.co), left=tuple(k.handle_left), right=tuple(k.handle_right),
                           **{name: getattr(k, name) for name in KEY_FIELDS}))
    return result


def restore(fc, keys):
    fc.keyframe_points.clear()
    fc.keyframe_points.add(len(keys))
    for k, saved in zip(fc.keyframe_points, keys):
        k.co = saved['co']
        for name in KEY_FIELDS:
            setattr(k, name, saved[name])
        k.handle_left = saved['left']
        k.handle_right = saved['right']
    fc.update()


def restore_exact(fc, keys):
    """Rebuild, then restore saved handles without another auto-handle solve.

    Partial reduction must not let Auto/Continuous Acceleration recalculate
    tangents on untouched keys. Coordinates and types outside the edit remain
    byte-for-byte identical in Blender's float storage.
    """
    return complete(restore_exact_steps(fc, keys))


def restore_exact_steps(fc, keys):
    fc.keyframe_points.clear()
    fc.keyframe_points.add(len(keys))
    for index, (key, saved) in enumerate(zip(fc.keyframe_points, keys)):
        if index % 128 == 0:
            yield
        key.co = saved['co']
        for name in KEY_FIELDS:
            setattr(key, name, saved[name])
        key.handle_left = saved['left']
        key.handle_right = saved['right']
    fc.update()
    for index, (key, saved) in enumerate(zip(fc.keyframe_points, keys)):
        if index % 128 == 0:
            yield
        key.handle_left = saved['left']
        key.handle_right = saved['right']


def sample_grid(times, step):
    first, last = times[0], times[-1]
    if (last-first)/step > 100000:
        raise ValueError('Range too long: limit of 100,000 samples per curve.')
    return sorted(set(times) | {round(first+i*step, 8)
                  for i in range(int((last-first)/step)+1)} | {last})


def group_kind(path):
    return TRANSFORMS.get(path.rsplit('.', 1)[-1])


def group_tolerance(kind, settings):
    base = settings.position_error if kind == 'LOCATION' else (
        settings.scale_error if kind == 'SCALE' else settings.rotation_error)
    return max(1e-8, base * settings.strength)


def write_group(curves, times, values, keep, originals, interpolation):
    ordered = sorted(keep)
    for axis, fc in enumerate(curves):
        types = {round(k['co'][0], 6): k['type'] for k in originals[axis]}
        fc.keyframe_points.clear()
        fc.keyframe_points.add(len(ordered))
        for k, i in zip(fc.keyframe_points, ordered):
            k.co = (times[i], values[i][axis])
            k.interpolation = interpolation
            k.handle_left_type = 'AUTO_CLAMPED'
            k.handle_right_type = 'AUTO_CLAMPED'
            k.type = types.get(round(times[i], 6), 'KEYFRAME')
        fc.update()
        if interpolation == 'BEZIER' and len(ordered) >= 2:
            # Auto-Clamped flattens the first/last tangent. Dense mocap usually
            # starts in motion, so preserve its boundary velocity explicitly.
            saved = originals[axis]
            for is_last in (False, True):
                endpoint = fc.keyframe_points[-1 if is_last else 0]
                neighbor = fc.keyframe_points[-2 if is_last else 1]
                src = saved[-1 if is_last else 0]
                other = saved[-2 if is_last else 1]
                incoming = saved[-2]['interpolation'] if is_last else src['interpolation']
                handle = src['left'] if is_last else src['right']
                dx = handle[0]-src['co'][0]
                slope = ((handle[1]-src['co'][1])/dx if incoming == 'BEZIER' and abs(dx)>1e-8
                         else (other['co'][1]-src['co'][1])/(other['co'][0]-src['co'][0]))
                length = abs(neighbor.co.x-endpoint.co.x)/3.0
                endpoint.handle_left_type = 'FREE'
                endpoint.handle_right_type = 'FREE'
                endpoint.handle_left = (endpoint.co.x-length, endpoint.co.y-slope*length)
                endpoint.handle_right = (endpoint.co.x+length, endpoint.co.y+slope*length)
            fc.update()


def reduce_group(curves, kind, settings):
    """Return actual output errors; fall back if smoothing cannot meet them.

    Output uses only source key times, synchronized across XYZ / WXYZ.
    Validation includes half frames and all original key times. This is a
    sampled local-transform bound, not a guarantee of world-space foot contact.
    """
    originals = [snapshot(fc) for fc in curves]
    before = sum(map(len, originals))
    if any(fc.lock or fc.mute or fc.modifiers or fc.sampled_points for fc in curves):
        return before, before, 0.0, 'Locked, muted, modified or sampled curves were preserved.'
    if any(k['interpolation'] not in {'LINEAR', 'BEZIER'} for keys in originals for k in keys):
        return before, before, 0.0, 'Constant or special interpolation was preserved.'
    if kind == 'QUATERNION' and [fc.array_index for fc in curves] != [0, 1, 2, 3]:
        return before, before, 0.0, 'Incomplete quaternion was preserved.'
    if any(len(keys) < 2 for keys in originals):
        return before, before, 0.0, ''
    # Different endpoints would change extrapolation if synchronized.
    if len({(round(k[0]['co'][0], 6), round(k[-1]['co'][0], 6)) for k in originals}) != 1:
        return before, before, 0.0, 'Channels with different endpoints were preserved.'
    times = sorted({float(k['co'][0]) for keys in originals for k in keys})
    if len(times) < 3:
        return before, before, 0.0, ''
    if len(times) > 20000:
        raise ValueError('More than 20,000 key times in one group. Reduce a shorter section.')
    values = [tuple(fc.evaluate(t) for fc in curves) for t in times]
    if any(not math.isfinite(x) for v in values for x in v):
        return before, before, 0.0, 'Non-finite values were preserved.'
    if kind == 'QUATERNION':
        if any(sum(x*x for x in v) < 1e-10 for v in values) or any(
                sum(x*y for x, y in zip(a, b)) <= 0 for a, b in zip(values, values[1:])):
            return before, before, 0.0, 'Quaternion sign discontinuity was preserved.'
    tolerance = group_tolerance(kind, settings)
    protected = set()
    if settings.preserve_extrema:
        protected |= extrema_indices(values, tolerance, kind)
    if settings.preserve_marked:
        marked = {float(k['co'][0]) for keys in originals for k in keys
                  if k['type'] in {'EXTREME', 'BREAKDOWN'}}
        protected |= {i for i, t in enumerate(times) if t in marked}
    keep = reduce_indices(times, values, tolerance, kind, protected)
    checks = sample_grid(times, settings.sample_step)
    reference = [tuple(fc.evaluate(t) for fc in curves) for t in checks]
    # Refinement validates the *actual* Blender Bezier interpolation, not a
    # linear proxy. If no safe reduction exists, retain the exact source.
    for iteration in range(64):
        if len(keep)*len(curves) >= before:
            break
        write_group(curves, times, values, keep, originals, settings.interpolation)
        errors = [distance(tuple(fc.evaluate(t) for fc in curves), v, kind)
                  for t, v in zip(checks, reference)]
        worst = max(errors, default=0.0)
        if worst <= tolerance*(1.0+1e-5):
            return before, len(keep)*len(curves), worst, ''
        retained = sorted(keep)
        segments = {}
        for t, error in zip(checks, errors):
            if error <= tolerance:
                continue
            pos = bisect.bisect_right([times[i] for i in retained], t)
            lo, hi = retained[max(0, pos-1)], retained[min(pos, len(retained)-1)]
            if hi <= lo+1:
                # Auto handles at the ends can improve when their neighbors
                # are refined. Try nearby source key times first.
                lo, hi = max(0, lo-2), min(len(times)-1, hi+2)
            key = (lo, hi)
            if key not in segments or error > segments[key][1]:
                segments[key] = (t, error)
        additions = set()
        for (lo, hi), (t, _) in segments.items():
            options = [i for i in range(lo, hi+1) if i not in keep]
            if options:
                additions.add(min(options, key=lambda i: abs(times[i]-t)))
        if not additions:
            break
        keep |= additions
    for fc, keys in zip(curves, originals):
        restore(fc, keys)
    return before, before, 0.0, ''


def reduce_action(action, slot, settings, progress=None):
    return complete(reduce_action_steps(action, slot, settings, progress))


def reduce_action_steps(action, slot, settings, progress=None):
    import json
    if settings.method not in {'REDUCE', 'SIMPLIFY'}:
        raise ValueError('Unknown curve operation.')
    if settings.method == 'SIMPLIFY' and settings.key_selection is None:
        raise ValueError('Simplify Curve requires selected keys in the Graph Editor.')
    if settings.method == 'SIMPLIFY' and settings.simplify_mode not in {'KEEP', 'FIT'}:
        raise ValueError('Unknown simplification mode.')
    all_curves = slot_curves(action, slot)
    report = Report(before=sum(len(fc.keyframe_points) for fc in all_curves))
    groups = {}
    selection = None if settings.key_selection is None else {
        (entry['data_path'], entry['array_index']): set(entry['frames'])
        for entry in settings.key_selection if entry['frames']}
    if selection == {}:
        raise ValueError('No keys selected: select key points in the Graph Editor.')
    for fc in all_curves:
        kind = group_kind(fc.data_path)
        if kind is None:
            if settings.method == 'SIMPLIFY' and selection.get((fc.data_path, fc.array_index)):
                warning = 'Unsupported selected curves were preserved; select location, rotation or scale keys.'
                if warning not in report.warnings:
                    report.warnings.append(warning)
            continue
        match = BONE_PATH.match(fc.data_path)
        if settings.selected_bones is not None:
            if not match or json.loads(match.group(1)) not in settings.selected_bones:
                continue
        # Simplify keeps each scalar transform curve independent. Quaternion
        # components must still be processed and checked as an orientation.
        axis = fc.array_index if settings.method == 'SIMPLIFY' and kind != 'QUATERNION' else None
        groups.setdefault((fc.data_path, kind, axis), []).append(fc)
    if not groups:
        raise ValueError('No transform curves in the selection or active slot.')
    for number, ((path, kind, axis), curves) in enumerate(groups.items()):
        curves.sort(key=lambda c: c.array_index)
        def scope_count():
            count = 0
            for fc in curves:
                frames = None if selection is None else selection.get((fc.data_path, fc.array_index), set())
                for index, key in enumerate(fc.keyframe_points):
                    if index % 256 == 0:
                        yield
                    count += frames is None or float(key.co.x) in frames
            return count
        scope_before = yield from scope_count()
        if settings.method == 'SIMPLIFY':
            from .simplify import simplify_selected_group_steps
            before, after, error, warning = yield from simplify_selected_group_steps(curves, kind, settings, selection)
        elif selection is None:
            before, after, error, warning = reduce_group(curves, kind, settings)
        else:
            from .selection import reduce_selected_group
            before, after, error, warning = reduce_selected_group(curves, kind, settings, selection)
        report.reduced_groups += after < before
        report.preserved_groups += after == before
        scope_after = yield from scope_count()
        report.scope_before += scope_before
        report.scope_after += scope_after
        if scope_before:
            report.curve_details.append(dict(data_path=path, axis=axis, kind=kind,
                before=scope_before, after=scope_after, max_error=error,
                tolerance=group_tolerance(kind, settings), warning=warning))
        report.max_error_ratio = max(report.max_error_ratio, error/group_tolerance(kind, settings))
        if kind == 'LOCATION':
            report.max_position_error = max(report.max_position_error, error)
        elif kind == 'SCALE':
            report.max_scale_error = max(report.max_scale_error, error)
        else:
            report.max_rotation_error = max(report.max_rotation_error, error)
        if warning and warning not in report.warnings:
            report.warnings.append(warning)
        if progress:
            progress(number+1, len(groups))
        yield
    report.after = sum(len(fc.keyframe_points) for fc in all_curves)
    return report
