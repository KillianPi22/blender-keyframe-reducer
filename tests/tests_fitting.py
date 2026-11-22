"""Editable Bezier behavior on generated bone curves, with independent checks."""
import json
import math
import os
from pathlib import Path
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
import keyframe_reducer as addon
from keyframe_reducer.core import distance
from keyframe_reducer.engine import Settings, reduce_action, snapshot, slot_curves
from keyframe_reducer.fitting import hermite
from curve_cases import bone_cases

addon.register()
checks = []
output = Path(os.environ['KR_TEST_OUTPUT'])


def check(name, condition):
    assert condition, name
    checks.append(name)
    print('PASS', name, flush=True)


def new_action(name):
    action = bpy.data.actions.new(name)
    slot = action.slots.new(id_type='OBJECT', name=rig.name)
    bag = action.layers.new('Layer').strips.new(type='KEYFRAME').channelbag(slot, ensure=True)
    return action, slot, bag


def curve(bag, path, axis, values, interpolation='BEZIER', times=None):
    fc = bag.fcurves.new(path, index=axis)
    fc.keyframe_points.add(len(values))
    for key, t, value in zip(fc.keyframe_points, times or range(1, len(values)+1), values):
        key.co = (t, value)
        key.interpolation = interpolation
        key.handle_left_type = key.handle_right_type = 'AUTO_CLAMPED'
        key.select_control_point = True
        key.select_left_handle = key.select_right_handle = False
    fc.update()
    return fc


def capture(curves, frames=None):
    return [{'data_path': fc.data_path, 'array_index': fc.array_index,
             'frames': [float(k.co.x) for k in fc.keyframe_points if frames is None or k.co.x in frames]}
            for fc in curves]


def signature(action, slot=None):
    return [snapshot(fc) for fc in slot_curves(action, slot or action.slots[0])]


def run(source, mask, **options):
    dest = source.copy()
    settings = Settings(method='SIMPLIFY', simplify_mode='FIT', key_selection=mask, **options)
    report = reduce_action(dest, dest.slots[0], settings)
    return dest, report


data = bpy.data.armatures.new('TestSkeleton')
rig = bpy.data.objects.new('EditableCurveRig', data)
bpy.context.collection.objects.link(rig)
for ob in bpy.context.selected_objects:
    ob.select_set(False)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='EDIT')
upper = data.edit_bones.new('Upper')
upper.head, upper.tail = (0, 0, 0), (0, 1, 0)
lower = data.edit_bones.new('Lower')
lower.head, lower.tail = (0, 1, 0), (0, 2, 0)
lower.parent = upper
bpy.ops.object.mode_set(mode='POSE')
for bone in rig.pose.bones:
    bone.rotation_mode = 'XYZ'
path = 'pose.bones["Upper"].rotation_euler'
child_path = 'pose.bones["Lower"].rotation_euler'

# A baked multi-pose curve with a shoulder, peaks and troughs, like an editing
# exercise. This is generated data, not the user's character animation.
anchors = [(1, 0), (31, 40), (61, -10), (91, 38), (121, 43),
           (151, -10), (181, 40), (211, 0), (241, 60)]
def motion(t):
    for (a, av), (b, bv) in zip(anchors, anchors[1:]):
        if t <= b:
            return hermite((math.radians(av),), (math.radians(bv),), (0,), (0,), b-a, (t-a)/(b-a))[0]

source, slot, bag = new_action('BakedBoneMotion')
fc = curve(bag, path, 2, [motion(t) for t in range(1, 242)])
child = curve(bag, child_path, 0, [math.sin(t/50)*0.2 for t in range(241)])
all_mask = capture([fc, child])
originals = signature(source)
other_slot = source.slots.new(id_type='OBJECT', name='Unrelated')
other_bag = source.layers[0].strips[0].channelbag(other_slot, ensure=True)
curve(other_bag, 'location', 0, range(20))
unrelated = signature(source, other_slot)
samples = [1+i/8 for i in range(1921)]
comparison = {'reference': [(t, fc.evaluate(t)) for t in samples], 'results': {}}
for mode in ('KEEP', 'FIT'):
    dest = source.copy()
    start = time.perf_counter()
    settings = Settings(method='SIMPLIFY', simplify_mode=mode, key_selection=all_mask,
                        selected_bones={'Upper'}, preserve_manual=False)
    report = reduce_action(dest, dest.slots[0], settings)
    seconds = time.perf_counter()-start
    target = slot_curves(dest, dest.slots[0])[0]
    error = max(abs(target.evaluate(t)-fc.evaluate(t)) for t in samples)
    comparison['results'][mode] = dict(before=report.scope_before, after=report.scope_after,
        error_degrees=math.degrees(error), seconds=seconds, keys=snapshot(target),
        samples=[(t, target.evaluate(t)) for t in samples])
    if mode == 'FIT':
        fitted, fit_report, fit_curve = dest, report, target
check('fitted bone curve needs less than half the legacy keys at equal tolerance',
      fit_report.scope_after < comparison['results']['KEEP']['after']/2)
check('fitted error checked independently at eighth frames',
      comparison['results']['FIT']['error_degrees'] <= 0.5)
check('shoulder recovers nine useful controls', fit_report.scope_after == 9)
check('shoulder control lies at the slowdown', 91 in {k.co.x for k in fit_curve.keyframe_points})
check('source bone curves and unrelated slot unchanged', signature(source) == originals and
      signature(fitted, fitted.slots[1]) == unrelated)
check('selected bone filter preserves other bones', signature(fitted)[1] == originals[1])
check('scope statistics exclude filtered bones', fit_report.scope_before == 241 and
      len(fit_report.curve_details) == 1 and fit_report.curve_details[0]['data_path'] == path)
check('surviving bone keys retain source values and times', all(
      k['co'] in {v['co'] for v in originals[0]} for k in snapshot(fit_curve)))
check('editable interior handles are aligned', all(k.handle_left_type == k.handle_right_type == 'ALIGNED'
      and k.interpolation == 'BEZIER' for k in fit_curve.keyframe_points[1:-1]))
check('fitted tangents share velocity across interior keys', all(abs(
      (k.co.y-k.handle_left.y)/(k.co.x-k.handle_left.x) -
      (k.handle_right.y-k.co.y)/(k.handle_right.x-k.co.x)) < 1e-5
      for k in fit_curve.keyframe_points[1:-1]))

# Also evaluate an actual parented skeleton, not just the scalar curve.
positions = []
for action in (source, fitted):
    addon.assign(rig, action, slot.identifier)
    points = []
    for t in range(1, 242, 2):
        bpy.context.scene.frame_set(t)
        points.append((rig.matrix_world @ rig.pose.bones['Lower'].tail).copy())
    positions.append(points)
tip_error = max((a-b).length for a, b in zip(*positions))
check('generated skeleton stays inside its measured angular displacement bound',
      tip_error < 4*math.sin(math.radians(0.5)/2)+1e-6)
comparison['generated_two_bone_tip_error_world_units'] = tip_error

# A single smooth cubic can be represented by its two endpoint controls.
cubic, cs, cb = new_action('Cubic')
c = curve(cb, path, 2, [(i/120)**2*(3-2*(i/120)) for i in range(121)], 'LINEAR')
co, cr = run(cubic, capture([c]), rotation_error=0.001)
check('two-key ease uses fitted tangents instead of linear seed keys', cr.scope_after == 2)
check('linear baked input explicitly becomes Bezier', slot_curves(co, co.slots[0])[0].keyframe_points[0].interpolation == 'BEZIER')

# Close adaptive anchors around fast transitions can become redundant once
# adjoining tangents have been solved. Removing them must keep the same shape
# tolerance, measured independently from the fitter's quarter-frame grid.
steep, sts, stb = new_action('SteepTransitions')
stc = curve(stb, path, 2, [.8/(1+math.exp(-(t-70)/3)) -
                         .9/(1+math.exp(-(t-160)/7)) for t in range(241)])
sto, strp = run(steep, capture([stc]))
stf = slot_curves(sto, sto.slots[0])[0]
check('fast transitions use at most ten editable controls', strp.scope_after <= 10)
check('pruned fast transitions retain sampled shape', max(abs(stf.evaluate(t)-stc.evaluate(t))
      for t in samples) <= math.radians(.5))

# More difficult shapes and finer independent checks. Large oscillations must
# not disappear merely to achieve an attractive key count.
limits = {'long_holds': 6, 'small_ripple': 4, 'mixed_arcs': 36,
          'weighted_ease': 3, 'brief_gesture': 5}
for name, count, function in bone_cases():
    if name in {'shoulder', 'fast_transitions'}:
        continue
    action, case_slot, case_bag = new_action(name)
    original = curve(case_bag, path, 2, [function(t) for t in range(count)])
    saved = snapshot(original)
    result, report = run(action, capture([original]))
    target = slot_curves(result, result.slots[0])[0]
    error = max(abs(original.evaluate(1+i/16)-target.evaluate(1+i/16))
                for i in range((count-1)*16+1))
    check(name+' keeps shape at sixteenth frames', error <= math.radians(.5))
    check(name+' leaves source untouched', snapshot(original) == saved)
    if name in limits:
        check(name+' uses sparse controls', report.scope_after <= limits[name])
    else:
        check('visible oscillations remain represented', report.scope_after > 60)
        broad, broad_report = run(action, capture([original]), rotation_error=math.radians(1))
        broad_curve = slot_curves(broad, broad.slots[0])[0]
        check('narrow error peak triggers finer validation', max(abs(
            original.evaluate(1+i/16)-broad_curve.evaluate(1+i/16))
            for i in range((count-1)*16+1)) <= math.radians(1))

# Deterministic mixed-frequency motion at three detail levels exercises cases
# that were not used to choose the sparse-key examples above.
randomizer = random.Random(4861)
for case in range(8):
    action, random_slot, random_bag = new_action('MixedFrequency'+str(case))
    phase, rate = randomizer.uniform(0, math.tau), randomizer.uniform(.7, 2.1)
    amplitude = randomizer.uniform(.002, .025)
    original = curve(random_bag, path, 2, [.4*math.sin(t/19+phase) +
        .15*math.sin(t/7) + amplitude*math.sin(t*rate) for t in range(181)])
    tolerance = math.radians((.25, .5, 1.)[case % 3])
    result, report = run(action, capture([original]), rotation_error=tolerance)
    target = slot_curves(result, result.slots[0])[0]
    check('mixed-frequency shape '+str(case)+' stays within tolerance', max(abs(
        original.evaluate(1+i/16)-target.evaluate(1+i/16)) for i in range(180*16+1)) <= tolerance)

# Marked controls survive both anchor removal and relocation around shoulders.
fc.keyframe_points[88].type = 'BREAKDOWN'
protected, protected_report = run(source, capture([fc]))
check('consolidation preserves marked shoulder controls', any(k.co.x == 89 and k.type == 'BREAKDOWN'
      for k in slot_curves(protected, protected.slots[0])[0].keyframe_points))
fc.keyframe_points[88].type = 'KEYFRAME'

# Linear progress through multiple turns must never be modulo-wrapped.
spin, ss, sb = new_action('FullEulerTurns')
spin_curve = curve(sb, path, 2, [i*math.tau/30 for i in range(121)], 'LINEAR')
sp, spr = run(spin, capture([spin_curve]))
check('unwrapped Euler turns survive fitting', spr.scope_after == 2 and
      abs(slot_curves(sp, sp.slots[0])[0].evaluate(61)-2*math.tau) < 1e-5)

# Partial edits must retain all unselected data and motion in adjacent spans.
partial_mask = set(range(21, 72)) | set(range(131, 192)) | {220}
po, pr = run(source, capture([fc], partial_mask))
pc = slot_curves(po, po.slots[0])[0]
check('disjoint runs actually fit', pr.scope_after < pr.scope_before)
check('all selected boundaries and isolated keys survive',
      {21, 71, 131, 191, 220} <= {k.co.x for k in pc.keyframe_points})
check('unselected metadata and handles survive exactly',
      [k for k in snapshot(pc) if k['co'][0] not in partial_mask] ==
      [k for k in originals[0] if k['co'][0] not in partial_mask])
check('outside motion is identical at subframes', max(abs(pc.evaluate(t)-fc.evaluate(t))
      for t in samples if not (21 <= t <= 71 or 131 <= t <= 191)) < 1e-7)
check('partial fit measured shape stays within angular tolerance',
      max(abs(pc.evaluate(t)-fc.evaluate(t)) for t in samples) <= math.radians(0.5))

# A marked pose remains at the exact time and value, even on a simple slope.
spin_curve.keyframe_points[45].type = 'BREAKDOWN'
marked, mr = run(spin, capture([spin_curve]))
check('marked pose preserved in editable fit', any(k.co.x == 46 and k.type == 'BREAKDOWN'
      for k in slot_curves(marked, marked.slots[0])[0].keyframe_points))

# Protection of old manual handles belongs to KEEP. FIT explicitly rebuilds
# them, and does not make a mocap bake with FREE handles an uneditable no-op.
manual, mas, mab = new_action('ManualBake')
mc = curve(mab, path, 2, [i/100 for i in range(101)])
for key in mc.keyframe_points:
    key.handle_left_type = key.handle_right_type = 'FREE'
    key.handle_left = (key.co.x-1/3, key.co.y-0.01/3)
    key.handle_right = (key.co.x+1/3, key.co.y+0.01/3)
mo, mreport = run(manual, capture([mc]), preserve_manual=True)
check('explicit fit rebuilds dense manual handles', mreport.scope_after == 2)

# A narrow overshoot that lives only in manual handles cannot be erased by
# looking only at equal-valued key points.
sub, subs, subb = new_action('HiddenSubframeOvershoot')
subc = curve(subb, path, 2, [0.0]*5, times=[1+i*.1 for i in range(5)])
for key in subc.keyframe_points:
    key.handle_left_type = key.handle_right_type = 'FREE'
    key.handle_left = (key.co.x-.03, 0)
    key.handle_right = (key.co.x+.03, 0)
subc.keyframe_points[2].handle_right.y = 2
sub_saved = signature(sub)
subo, subr = run(sub, capture([subc]))
check('unrepresentable between-key overshoot falls back exactly', signature(subo) == sub_saved and bool(subr.warnings))

# WXYZ still share times and are checked in orientation space.
quat, qs, qb = new_action('QuaternionFit')
qp = 'pose.bones["Upper"].rotation_quaternion'
qc = [curve(qb, qp, axis, [math.cos(i/100) if axis == 0 else math.sin(i/100)
       if axis == 3 else 0 for i in range(121)]) for axis in range(4)]
qo, qr = run(quat, capture(qc))
qout = slot_curves(qo, qo.slots[0])
check('quaternion fit reduces with common WXYZ times', qr.after < qr.before and
      len({tuple(k.co.x for k in fc.keyframe_points) for fc in qout}) == 1)
check('quaternion fit independently checked in angular units', max(distance(
      tuple(fc.evaluate(1+i/8) for fc in qc), tuple(fc.evaluate(1+i/8) for fc in qout),
      'QUATERNION') for i in range(961)) <= math.radians(0.5))
incomplete, ir = run(quat, capture(qc[:1]))
check('partial quaternion fitting is rejected safely', signature(incomplete) == signature(quat) and bool(ir.warnings))
qc[0].keyframe_points[40].co.y *= -1
signed, sr = run(quat, capture(qc))
check('quaternion sign discontinuity is preserved', signature(signed) == signature(quat) and bool(sr.warnings))

complex_q, cqs, cqb = new_action('ChangingQuaternionAxes')
qvalues = []
for t in range(241):
    a, b = .5*math.sin(t/37), .4*math.sin(t/19)
    qvalues.append((math.cos(a)*math.cos(b), math.sin(a)*math.cos(b),
                    math.cos(a)*math.sin(b), math.sin(a)*math.sin(b)))
complex_curves = [curve(cqb, qp, axis, [v[axis] for v in qvalues]) for axis in range(4)]
complex_saved = signature(complex_q)
complex_result, complex_report = run(complex_q, capture(complex_curves))
complex_fitted = slot_curves(complex_result, complex_result.slots[0])
check('changing-axis quaternion fit keeps shared times', complex_report.scope_after < 964 and
      len({tuple(k.co.x for k in fc.keyframe_points) for fc in complex_fitted}) == 1)
check('changing-axis quaternion fit respects angular error at sixteenth frames', max(distance(
    tuple(fc.evaluate(1+i/16) for fc in complex_curves),
    tuple(fc.evaluate(1+i/16) for fc in complex_fitted), 'QUATERNION')
    for i in range(240*16+1)) <= math.radians(.5))
check('changing-axis quaternion source stays untouched', signature(complex_q) == complex_saved)

# Unsupported curve features must stay untouched in this mode as well.
for flag in ('lock', 'mute', 'hide', 'modifier', 'constant'):
    blocked, bs, bb = new_action(flag)
    bc = curve(bb, path, 2, range(20), 'CONSTANT' if flag == 'constant' else 'BEZIER')
    if flag == 'modifier':
        bc.modifiers.new('NOISE')
    elif flag != 'constant':
        setattr(bc, flag, True)
    bo, br = run(blocked, capture([bc]))
    check(flag+' is preserved in fit mode', signature(bo) == signature(blocked) and bool(br.warnings))

# Actual operators: scope accounting and persistence on an armature.
addon.assign(rig, source, slot.identifier)
rig.pose.bones['Upper'].select = True
rig.pose.bones['Lower'].select = False
data.bones.active = data.bones['Upper']
st = rig.kr_settings
st.position_error, st.scale_error = .075, .002
tolerances = st.position_error, st.rotation_error, st.scale_error
action_count = len(bpy.data.actions)
check('bone animation profile prepares explicit fitting', bpy.ops.kr.animation_profile() == {'FINISHED'} and
      st.method == 'SIMPLIFY' and st.simplify_mode == 'FIT' and st.selected_only and
      st.preserve_extrema and st.preserve_marked)
check('profile preserves tolerances and does not run or mutate animation',
      tolerances == (st.position_error, st.rotation_error, st.scale_error) and
      len(bpy.data.actions) == action_count and rig.animation_data.action == source and signature(source) == originals)
area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
area.type = 'GRAPH_EDITOR'
area.spaces.active.mode = 'FCURVES'
region = next(r for r in area.regions if r.type == 'UI')
with bpy.context.temp_override(area=area, region=region):
    check('bone fit operator works in Graph Editor sidebar', bpy.ops.kr.reduce() == {'FINISHED'})
    first = signature(st.reduced)
    check('new result matches displayed settings', not addon.result_needs_update(rig))
    check('panel statistics reflect the selected bone', st.scope_before == 241 and st.scope_after < 20)
    st.rotation_error = math.radians(1)
    check('tolerance change marks previous result as stale', addon.result_needs_update(rig))
    bpy.ops.kr.reduce()
    st.rotation_error = math.radians(.5)
    bpy.ops.kr.reduce()
    check('A B A fitting returns to the same result from source', signature(st.reduced) == first and st.source == source)
    check('recalculation clears stale result indication', not addon.result_needs_update(rig))
    st.simplify_mode = 'KEEP'
    bpy.ops.kr.reduce()
    st.simplify_mode = 'FIT'
    bpy.ops.kr.reduce()
    check('switching curve style does not accumulate reductions', signature(st.reduced) == first and st.source == source)
    # Empty bone selection cannot turn into processing all bones.
    count, current = len(bpy.data.actions), st.reduced
    rig.pose.bones['Upper'].select = False
    check('changing bone scope marks result as stale', addon.result_needs_update(rig))
    try:
        addon.run_reduction(bpy.context)
    except ValueError:
        pass
    else:
        raise AssertionError('Missing bone selection must reject')
    check('empty bone filter fails atomically', st.reduced == current and len(bpy.data.actions) == count)
    rig.pose.bones['Upper'].select = True

scratch = output/'editable_bone_curves.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(scratch), check_existing=False)
bpy.ops.wm.open_mainfile(filepath=str(scratch), load_ui=False)
rig = bpy.data.objects['EditableCurveRig']
bpy.context.view_layer.objects.active = rig
st = rig.kr_settings
check('fit style and editable handles persist after reopen', st.simplify_mode == 'FIT' and signature(st.reduced) == first)
check('fit recalculates after reopen', bpy.ops.kr.reduce() == {'FINISHED'} and signature(st.reduced) == first)
bpy.ops.ed.undo_push(message='Before Bezier Fit Change')
st.rotation_error = math.radians(1)
bpy.ops.kr.reduce()
bpy.ops.ed.undo_push(message='After Bezier Fit Change')
bpy.ops.ed.undo()
rig = bpy.data.objects['EditableCurveRig']
check('undo restores fitted result and handles', signature(rig.kr_settings.reduced) == first)
bpy.ops.ed.redo()
rig = bpy.data.objects['EditableCurveRig']
check('redo restores fitting settings and comparison', addon.current_pair(rig) and
      abs(rig.kr_settings.rotation_error-math.radians(1)) < 1e-6)
check('all operator operations leave source curves untouched', signature(rig.kr_settings.source) == originals)

(output/'fit_comparison.json').write_text(json.dumps(comparison, indent=2))
print('FITTING_TEST_SUMMARY', json.dumps({'passed': True, 'checks': len(checks),
      'version': bpy.app.version_string, 'legacy_keys': comparison['results']['KEEP']['after'],
      'fitted_keys': comparison['results']['FIT']['after'],
      'max_error_degrees': comparison['results']['FIT']['error_degrees'],
      'generated_tip_error': tip_error}), flush=True)
