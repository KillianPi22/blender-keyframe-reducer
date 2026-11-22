"""Behavior regressions for source-preserving selected-curve simplification."""
import importlib
import json
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
import keyframe_reducer as addon
from keyframe_reducer.core import distance
from keyframe_reducer.engine import Settings, reduce_action, slot_curves, snapshot

addon.register()
checks = []


def check(name, condition):
    assert condition, name
    checks.append(name)
    print('PASS', name, flush=True)


def new_action(name):
    action = bpy.data.actions.new(name)
    slot = action.slots.new(id_type='OBJECT', name=ob.name)
    strip = action.layers.new('Layer').strips.new(type='KEYFRAME')
    return action, slot, strip.channelbag(slot, ensure=True)


def curve(bag, path, index, values, interpolation='BEZIER'):
    fc = bag.fcurves.new(path, index=index)
    fc.auto_smoothing = 'CONT_ACCEL'
    for frame, value in enumerate(values, 1):
        key = fc.keyframe_points.insert(frame, value)
        key.interpolation = interpolation
        key.handle_left_type = key.handle_right_type = 'AUTO_CLAMPED'
        key.select_control_point = key.select_left_handle = key.select_right_handle = False
    fc.update()
    return fc


def select(curves, mapping):
    for fc in curves:
        for key in fc.keyframe_points:
            key.select_control_point = key.co.x in mapping.get((fc.data_path, fc.array_index), set())
    return [{'data_path': fc.data_path, 'array_index': fc.array_index,
             'frames': [float(k.co.x) for k in fc.keyframe_points if k.select_control_point]}
            for fc in curves if any(k.select_control_point for k in fc.keyframe_points)]


def signature(action, slot=None):
    return [snapshot(fc) for fc in slot_curves(action, slot or action.slots[0])]


def simplified(source, selection, **options):
    result = source.copy()
    report = reduce_action(result, result.slots[0], Settings(
        method='SIMPLIFY', key_selection=selection, **options))
    return result, report


ob = bpy.data.objects.new('SimplifyTest', None)
bpy.context.collection.objects.link(ob)
for other in bpy.context.selected_objects:
    other.select_set(False)
ob.select_set(True)
bpy.context.view_layer.objects.active = ob

source, slot, bag = new_action('Source')
x = curve(bag, 'location', 0, [i/10 + math.sin(i/8)*0.04 for i in range(101)])
y = curve(bag, 'location', 1, [i/5 for i in range(101)], 'LINEAR')
z = curve(bag, 'location', 2, [math.sin(i/10) for i in range(101)])
custom = curve(bag, '["custom"]', 0, [i/10 for i in range(101)])
islands = set(range(11, 32)) | set(range(51, 72)) | {91}
mask = select([x, y, z, custom], {('location', 0): islands, ('location', 1): set(range(14, 26)),
                                        ('["custom"]', 0): set(range(1, 102))})
originals = signature(source)
other_slot = source.slots.new(id_type='OBJECT', name='Unrelated')
other_bag = source.layers[0].strips[0].channelbag(other_slot, ensure=True)
curve(other_bag, 'location', 0, range(20))
other_original = signature(source, other_slot)
result, report = simplified(source, mask, position_error=0.02, sample_step=0.25)
rx, ry, rz, rc = slot_curves(result, result.slots[0])
check('source and unrelated slot unchanged', signature(source) == originals and
      signature(result, result.slots[1]) == other_original)
check('independent axes with different selected windows simplify',
      len(rx.keyframe_points) < len(x.keyframe_points) and len(ry.keyframe_points) == 91)
check('unselected channels and unsupported custom curves unchanged', snapshot(rz) == originals[2] and snapshot(rc) == originals[3])
check('outside keys and metadata exact', [k for k in snapshot(rx) if k['co'][0] not in islands] ==
      [k for k in originals[0] if k['co'][0] not in islands])
check('islands boundaries and isolated key kept', {11, 31, 51, 71, 91} <= {k.co.x for k in rx.keyframe_points})
check('retained values and interpolation come from source', all(
    (k['co'], k['interpolation'], k['type'], k['select_control_point']) in
    {(s['co'], s['interpolation'], s['type'], s['select_control_point']) for s in originals[axis]}
    for axis, fc in enumerate([rx, ry]) for k in snapshot(fc)))
outside_error = max(abs(rx.evaluate(t/8)-x.evaluate(t/8)) for t in range(8, 809)
                    if not (11 <= t/8 <= 31 or 51 <= t/8 <= 71))
inside_error = max(abs(rx.evaluate(t/8)-x.evaluate(t/8)) for t in range(8, 809))
check('adjacent spans and gaps evaluate identically', outside_error < 1e-7)
check('independent finer sampled shape check', inside_error <= 0.02001)
check('linear interpolation remains linear', all(k.interpolation == 'LINEAR' for k in ry.keyframe_points))

# Manual tangents are protected by default, even on a redundant linear shape.
manual, ms, mb = new_action('ManualTangents')
mc = curve(mb, 'location', 0, range(21))
for key in mc.keyframe_points:
    key.handle_left_type = key.handle_right_type = 'FREE'
    key.handle_left = (key.co.x-1/3, key.co.y-1/3)
    key.handle_right = (key.co.x+1/3, key.co.y+1/3)
mask_manual = select([mc], {('location', 0): set(range(1, 22))})
manual_before = signature(manual)
protected, pr = simplified(manual, mask_manual)
unprotected, ur = simplified(manual, mask_manual, preserve_manual=False)
check('manual tangent keys protected by default', signature(protected) == manual_before)
check('manual tangent removal is opt in', ur.after < ur.before and
      max(abs(slot_curves(unprotected, unprotected.slots[0])[0].evaluate(t/8)-mc.evaluate(t/8))
          for t in range(8, 169)) < 1e-4)
mc.keyframe_points[10].type = 'BREAKDOWN'
marked, mr = simplified(manual, mask_manual, preserve_manual=False)
check('marked keys remain protected when tangent protection is off',
      11.0 in {k.co.x for k in slot_curves(marked, marked.slots[0])[0].keyframe_points})

# Subframe handles can hide an overshoot between equal-valued source keys.
overshoot, oslot, obag = new_action('SubframeOvershoot')
oc = curve(obag, 'location', 0, [0.0]*5)
for i, key in enumerate(oc.keyframe_points):
    key.co.x = 1+i*0.1
    key.handle_left_type = key.handle_right_type = 'FREE'
    key.handle_left = (key.co.x-0.03, 0.0)
    key.handle_right = (key.co.x+0.03, 0.0)
oc.keyframe_points[2].handle_right.y = 2
omask = select([oc], {('location', 0): {float(k.co.x) for k in oc.keyframe_points}})
out, oreport = simplified(overshoot, omask, preserve_manual=False, position_error=0.01)
outc = slot_curves(out, out.slots[0])[0]
check('between-key overshoot is retained',
      max(abs(outc.evaluate(1+i*0.001)-oc.evaluate(1+i*0.001)) for i in range(401)) <= 0.01001)

euler, es, eb = new_action('EulerTurns')
ec = curve(eb, 'rotation_euler', 2, [i*math.tau/30 for i in range(61)], 'LINEAR')
em = select([ec], {('rotation_euler', 2): set(range(1, 62))})
eout, er = simplified(euler, em)
check('full Euler turns retained in angular units', er.after < er.before and
      abs(slot_curves(eout, eout.slots[0])[0].evaluate(31)-math.tau) < 1e-5)
quaternion, qs, qb = new_action('Quaternion')
qc = [curve(qb, 'rotation_quaternion', axis,
            [math.cos(i/80) if axis == 0 else math.sin(i/80) if axis == 3 else 0 for i in range(81)])
      for axis in range(4)]
qm = select(qc, {('rotation_quaternion', axis): set(range(11, 72)) for axis in range(4)})
qo, qr = simplified(quaternion, qm, rotation_error=math.radians(0.5))
qout = slot_curves(qo, qo.slots[0])
check('complete quaternions simplify with synchronized keys', qr.after < qr.before and
      len({tuple(k.co.x for k in fc.keyframe_points) for fc in qout}) == 1)
check('independent orientation error check', max(
    distance(tuple(fc.evaluate(i/8) for fc in qc), tuple(fc.evaluate(i/8) for fc in qout), 'QUATERNION')
    for i in range(8, 649)) <= math.radians(0.5)*1.001)
partial, pp = simplified(quaternion, qm[:1])
check('partial quaternion selection unchanged and explained', signature(partial) == signature(quaternion) and
      any('Quaternion selection' in warning for warning in pp.warnings))
qc[0].keyframe_points[30].co.y *= -1
sign_before = signature(quaternion)
sign_result, sr = simplified(quaternion, qm)
check('quaternion sign discontinuity preserved', signature(sign_result) == sign_before and bool(sr.warnings))

for state in ('lock', 'hide', 'mute', 'modifier', 'constant'):
    blocked, bs, bb = new_action('Unsupported_'+state)
    bc = curve(bb, 'location', 0, range(21), 'CONSTANT' if state == 'constant' else 'BEZIER')
    if state == 'modifier':
        bc.modifiers.new('NOISE')
    elif state != 'constant':
        setattr(bc, state, True)
    bm = select([bc], {('location', 0): set(range(1, 22))})
    saved = signature(blocked)
    bout, br = simplified(blocked, bm)
    check(state+' curves preserved and explained', signature(bout) == saved and bool(br.warnings))

# Real Graph Editor operations, immutable recalc, comparison, undo, persistence.
addon.assign(ob, source, slot.identifier)
st = ob.kr_settings
st.method = 'SIMPLIFY'
st.scope = 'ACTION'  # Simplify must still use selected keys, never this scope.
st.position_error = 0.02
st.dense_check = True
area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
area.type = 'GRAPH_EDITOR'
area.spaces.active.mode = 'FCURVES'
area.spaces.active.dopesheet.show_only_selected = True
region = next(r for r in area.regions if r.type == 'WINDOW')
with bpy.context.temp_override(area=area, region=region):
    check('simplify operator in Graph Editor', bpy.ops.kr.reduce() == {'FINISHED'} and st.last_scope == 'KEYS')
    first = signature(st.reduced)
    first_name = st.reduced.name
    captured = st.selection_json
    st.position_error = 0.05
    bpy.ops.kr.reduce()
    check('superseded result cleaned up', first_name not in bpy.data.actions)
    st.position_error = 0.02
    bpy.ops.kr.reduce()
    check('A B A settings reproduce the same result from source', signature(st.reduced) == first and st.source == source)
    check('captured selection remains stable', st.selection_json == captured)
    st.method = 'REDUCE'
    st.scope = 'KEYS'
    bpy.ops.kr.reduce()
    st.method = 'SIMPLIFY'
    bpy.ops.kr.reduce()
    check('switching tools reuses source and captured selection', st.source == source and
          st.selection_json == captured and signature(st.reduced) == first)
    check('original comparison', bpy.ops.kr.compare(reduced=False) == {'FINISHED'} and ob.animation_data.action == source)
    check('simplified comparison', bpy.ops.kr.compare(reduced=True) == {'FINISHED'} and ob.animation_data.action == st.reduced)
    # An engine failure after mutating the disposable copy cannot publish it.
    original_reduce = addon.reduce_action
    current = st.reduced
    count = len(bpy.data.actions)
    def fail_after_reduce(*args, **kwargs):
        original_reduce(*args, **kwargs)
        raise RuntimeError('Injected validation failure')
    addon.reduce_action = fail_after_reduce
    try:
        addon.run_reduction(bpy.context)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Injected failure must propagate')
    finally:
        addon.reduce_action = original_reduce
    check('mid-calculation failure leaves source and comparison intact', st.reduced == current and
          ob.animation_data.action == current and len(bpy.data.actions) == count and signature(source) == originals)

    # Explicitly rebasing onto a fresh selection keeps earlier simplification.
    select(slot_curves(current, current.slots[0]), {('location', 0): set(range(36, 47))})
    current_x = snapshot(slot_curves(current, current.slots[0])[0])
    bpy.ops.kr.reduce(new_selection=True)
    new_x = snapshot(slot_curves(st.reduced, st.reduced.slots[0])[0])
    check('new selection rebases explicitly and preserves earlier result', st.source == current and
          [k for k in current_x if not 36 <= k['co'][0] <= 46] ==
          [k for k in new_x if not 36 <= k['co'][0] <= 46])
    before_count = len(bpy.data.actions)
    current = st.reduced
    select(slot_curves(current, current.slots[0]), {})
    try:
        addon.run_reduction(bpy.context, new_selection=True)
    except ValueError:
        pass
    else:
        raise AssertionError('Empty selection must reject')
    check('empty selection fails atomically', ob.animation_data.action == current and len(bpy.data.actions) == before_count)
    # Current source reload, not only immutable historical upgrade fixtures.
    addon.unregister()
    importlib.reload(addon)
    addon.register()
    st = ob.kr_settings
    st.method = 'SIMPLIFY'
    check('dependency-order package reload supports simplify',
          addon.Settings(method='SIMPLIFY').method == 'SIMPLIFY')
    addon.assign(ob, source, slot.identifier)
    st.position_error = 0.02
    bpy.ops.kr.reduce()
    check('simplify works after in-session reload', st.last_method == 'SIMPLIFY' and st.source == source)

output = Path(os.environ['KR_TEST_OUTPUT'])
path = output/'simplify.blend'
saved_result = signature(st.reduced)
saved_selection = st.selection_json
bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=False)
bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False)
ob = bpy.data.objects['SimplifyTest']
bpy.context.view_layer.objects.active = ob
st = ob.kr_settings
check('mode selection and result survive reopen', st.method == 'SIMPLIFY' and st.selection_json == saved_selection
      and signature(st.reduced) == saved_result)
check('recalculate after reopen', bpy.ops.kr.reduce() == {'FINISHED'} and signature(st.reduced) == saved_result)
with bpy.context.temp_override(area=next(a for a in bpy.context.screen.areas if a.type == 'GRAPH_EDITOR')):
    # The operator's published copy and captured state are undoable together.
    bpy.ops.ed.undo_push(message='Before Simplify Recalculate')
    st.position_error = 0.1
    bpy.ops.kr.reduce()
    bpy.ops.ed.undo_push(message='After Simplify Recalculate')
    bpy.ops.ed.undo()
    ob = bpy.data.objects['SimplifyTest']
    check('undo recalculation restores the earlier result and settings',
          signature(ob.kr_settings.reduced) == saved_result and abs(ob.kr_settings.position_error-0.02) < 1e-6)
    bpy.ops.ed.redo()
    ob = bpy.data.objects['SimplifyTest']
    check('redo recalculation restores the new result and settings',
          addon.current_pair(ob) and abs(ob.kr_settings.position_error-0.1) < 1e-6)
st = ob.kr_settings
source_name, result_name = st.source.name, st.reduced.name
bpy.ops.ed.undo_push(message='Before Restore Original')
check('restore original closes comparison', bpy.ops.kr.cancel() == {'FINISHED'} and
      ob.animation_data.action.name == source_name and st.source is None and st.reduced is None)
bpy.ops.ed.undo_push(message='After Restore Original')
bpy.ops.ed.undo()
ob = bpy.data.objects['SimplifyTest']
check('undo restores comparison and simplified Action', ob.animation_data.action.name == result_name and addon.current_pair(ob))
bpy.ops.ed.redo()
ob = bpy.data.objects['SimplifyTest']
check('redo restores source assignment', ob.animation_data.action.name == source_name and not addon.current_pair(ob))
check('source metadata never changed', signature(bpy.data.actions[source_name]) == originals)
print('SIMPLIFY_TEST_SUMMARY', json.dumps({'passed': True, 'checks': len(checks),
      'version': bpy.app.version_string, 'outside_max_error': outside_error, 'inside_max_error': inside_error}), flush=True)
