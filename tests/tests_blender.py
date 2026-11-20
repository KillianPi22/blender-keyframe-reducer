"""Run inside Blender --background --factory-startup --python this_file."""
import sys
import math
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
import keyframe_reducer as addon
from keyframe_reducer.engine import (Settings, reduce_action, slot_curves, snapshot,
                                     group_kind, group_tolerance)
from keyframe_reducer.core import distance, reduce_indices

addon.register()
checks = []


def check(name, expression):
    assert expression, name
    checks.append(name)
    print('PASS', name, flush=True)


def create_action(ob, name):
    ac = bpy.data.actions.new(name)
    slot = ac.slots.new(id_type='OBJECT', name=ob.name)
    layer = ac.layers.new('Layer')
    strip = layer.strips.new(type='KEYFRAME')
    bag = strip.channelbag(slot, ensure=True)
    return ac, slot, bag


def make_curve(bag, path, index, values, interpolation='LINEAR'):
    fc = bag.fcurves.new(path, index=index)
    for t, value in enumerate(values, 1):
        k = fc.keyframe_points.insert(t, value)
        k.interpolation = interpolation
    return fc


def signature(action, slot):
    return [(c.data_path, c.array_index, snapshot(c)) for c in slot_curves(action, slot)]


def verify(source, result, slot_id, settings):
    ss = source.slots[slot_id]
    rs = result.slots[slot_id]
    source_groups, target_groups = {}, {}
    for ac, slot, groups in ((source, ss, source_groups), (result, rs, target_groups)):
        for c in slot_curves(ac, slot):
            if group_kind(c.data_path):
                groups.setdefault(c.data_path, []).append(c)
    max_ratio = 0.0
    for path, curves in source_groups.items():
        curves.sort(key=lambda c:c.array_index)
        targets = sorted(target_groups[path], key=lambda c:c.array_index)
        kind = group_kind(path)
        times = [k.co.x for c in curves for k in c.keyframe_points]
        first, last = min(times), max(times)
        for i in range(int((last-first)/settings.sample_step)+1):
            t = first+i*settings.sample_step
            before = tuple(c.evaluate(t) for c in curves)
            after = tuple(c.evaluate(t) for c in targets)
            error = distance(before, after, kind)
            max_ratio = max(max_ratio, error/group_tolerance(kind, settings))
        check('endpoints '+path, all(
            abs(a.evaluate(t)-b.evaluate(t)) < 1e-5
            for a,b in zip(curves, targets) for t in (first,last)))
    check('independent sampled error bound', max_ratio <= 1.0001)
    return max_ratio


ob = bpy.data.objects.new('TestObject', None)
bpy.context.collection.objects.link(ob)
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
ac, slot, bag = create_action(ob, 'Synthetic')
for axis in range(3):
    make_curve(bag, 'location', axis, [math.sin(i/10)*(axis+1) for i in range(81)])
bag.fcurves[0].keyframe_points[20].type = 'BREAKDOWN'
for axis in range(3):
    make_curve(bag, 'scale', axis, [1.0]*81)
for axis in range(4):
    make_curve(bag, 'rotation_quaternion', axis,
               [(math.cos(i/40) if axis == 0 else math.sin(i/40) if axis == 3 else 0) for i in range(81)])
custom = make_curve(bag, '["custom"]', 0, [i%2 for i in range(81)], 'CONSTANT')
second_slot = ac.slots.new(id_type='OBJECT', name='Unrelated')
second_bag = ac.layers[0].strips[0].channelbag(second_slot, ensure=True)
make_curve(second_bag, 'location', 0, list(range(81)))
before = signature(ac, slot)
other_before = signature(ac, second_slot)
copy = ac.copy()
settings = Settings(position_error=0.02, rotation_error=math.radians(0.2), sample_step=0.25)
report = reduce_action(copy, copy.slots[0], settings)
print('SYNTHETIC_REPORT', report, flush=True)
print('COUNTS', [(c.data_path,c.array_index,len(c.keyframe_points)) for c in slot_curves(copy,copy.slots[0])], flush=True)
check('substantial synthetic reduction', report.after < report.before*0.5)
check('source untouched', signature(ac, slot) == before)
check('unrelated slot untouched', signature(copy, copy.slots[1]) == other_before)
check('custom property untouched', snapshot(slot_curves(copy, copy.slots[0])[-1]) == snapshot(custom))
location_curves = [fc for fc in slot_curves(copy, copy.slots[0]) if fc.data_path == 'location']
key_sets = [{k.co.x for k in fc.keyframe_points} for fc in location_curves]
check('XYZ aligned', all(x == key_sets[0] for x in key_sets))
check('marked pose retained on XYZ', all(21.0 in x for x in key_sets))
verify(ac, copy, 0, settings)

# Preserve full revolutions in Euler data; do not modulo angles.
euler, es, eb = create_action(ob, 'EulerSpin')
for axis in range(3):
    make_curve(eb, 'rotation_euler', axis, [i*math.tau/30 if axis == 2 else 0 for i in range(61)])
ecopy = euler.copy()
esettings = Settings(interpolation='LINEAR')
reduce_action(ecopy, ecopy.slots[0], esettings)
check('Euler double revolution retained', abs(slot_curves(ecopy, ecopy.slots[0])[2].evaluate(31)-math.tau) < 1e-5)
verify(euler, ecopy, 0, esettings)

# Locked groups, discontinuities, modifiers and sign-flipped quaternions.
locked, ls, lb = create_action(ob, 'Locked')
for axis in range(3):
    fc = make_curve(lb, 'location', axis, [i*.1 for i in range(20)])
    if axis == 0: fc.lock = True
for axis in range(4):
    make_curve(lb, 'rotation_quaternion', axis, [(-1 if i>10 else 1) if axis==0 else 0 for i in range(20)])
saved = signature(locked, ls)
lr = reduce_action(locked, ls, settings)
check('locked vector and quaternion sign change preserved', signature(locked, ls) == saved)
check('preservation warnings reported', len(lr.warnings) == 2)

# Real operators: copy protection, compare, re-run from source, no leaked previews.
addon.assign(ob, ac, slot.identifier)
st = ob.kr_settings
st.position_error = 0.02
st.dense_check = True
check('reduce operator', bpy.ops.kr.reduce() == {'FINISHED'})
first_result = st.reduced
first_name = first_result.name
check('original compare', bpy.ops.kr.compare(reduced=False) == {'FINISHED'} and ob.animation_data.action == ac)
check('reduced compare', bpy.ops.kr.compare(reduced=True) == {'FINISHED'} and ob.animation_data.action == first_result)
st.strength = 2.0
check('recalculate operator', bpy.ops.kr.reduce() == {'FINISHED'})
check('recalculation starts at original', st.source == ac)
check('unused previous preview cleaned', first_name not in bpy.data.actions)
check('source still untouched after operators', signature(ac, slot) == before)
check('finish operator', bpy.ops.kr.finish() == {'FINISHED'} and st.source is None and st.reduced is None)
check('original retained on save', ac.use_fake_user)

# Atomic failure: no abandoned Action and no reassignment if no transforms.
empty, empty_slot, empty_bag = create_action(ob, 'CustomOnly')
make_curve(empty_bag, '["property"]', 0, [1,2,3])
addon.assign(ob, empty, empty_slot.identifier)
count = len(bpy.data.actions)
try:
    addon.run_reduction(bpy.context)
except ValueError:
    pass
check('failure is atomic', len(bpy.data.actions) == count and ob.animation_data.action == empty)

addon.unregister()
print('TEST_SUMMARY', json.dumps({'version': bpy.app.version_string, 'checks': len(checks), 'passed': True}), flush=True)
