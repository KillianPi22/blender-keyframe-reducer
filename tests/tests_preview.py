"""Interactive preview lifecycle in real Blender, without wall-clock sleeps."""
import json
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
import keyframe_reducer as addon
from keyframe_reducer import preview
from keyframe_reducer.engine import Settings, reduce_action, slot_curves, snapshot
from keyframe_reducer.core import distance

addon.register()
preview.DEBOUNCE = 0.
checks = []
output = Path(os.environ['KR_TEST_OUTPUT'])


def check(name, value):
    assert value, name
    checks.append(name)
    print('PASS', name, flush=True)


data = bpy.data.armatures.new('PreviewSkeleton')
ob = bpy.data.objects.new('PreviewRig', data)
bpy.context.collection.objects.link(ob)
for other in bpy.context.selected_objects:
    other.select_set(False)
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.mode_set(mode='EDIT')
for name, x in [('Upper', 0), ('Other', 1)]:
    bone = data.edit_bones.new(name)
    bone.head, bone.tail = (x, 0, 0), (x, 1, 0)
bpy.ops.object.mode_set(mode='POSE')
for bone in ob.pose.bones:
    bone.rotation_mode = 'XYZ'
    bone.select = bone.name == 'Upper'
data.bones.active = data.bones['Upper']
source = bpy.data.actions.new('InteractiveSource')
slot = source.slots.new(id_type='OBJECT', name=ob.name)
bag = source.layers.new('Layer').strips.new(type='KEYFRAME').channelbag(slot, ensure=True)
for name in ('Upper', 'Other'):
    fc = bag.fcurves.new(f'pose.bones["{name}"].rotation_euler', index=2)
    fc.keyframe_points.add(361)
    for i, key in enumerate(fc.keyframe_points):
        key.co = (i+1, .5*math.sin(i/60)+.15*math.sin(i/17))
        key.interpolation = 'BEZIER'
        key.handle_left_type = key.handle_right_type = 'AUTO_CLAMPED'
        key.select_control_point = i < 300 or i >= 330
        key.select_left_handle = i == 12
        key.select_right_handle = i == 13
    fc.update()
extra_slot = source.slots.new(id_type='OBJECT', name='Unrelated')
extra_bag = source.layers[0].strips[0].channelbag(extra_slot, ensure=True)
extra_bag.fcurves.new('location', index=0).keyframe_points.insert(1, 10)
source['note'] = 'Keep me'
source['metadata'] = {'nested': [1, 2, 3], 'note': 'Keep this too'}
addon.assign(ob, source, slot.identifier)
identifier = slot.identifier
st = ob.kr_settings
st.method, st.simplify_mode, st.selected_only = 'SIMPLIFY', 'FIT', True
area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
area.type = 'GRAPH_EDITOR'
area.spaces.active.mode = 'FCURVES'
region = next(r for r in area.regions if r.type == 'UI')


def signature(action):
    return [[snapshot(fc) for fc in slot_curves(action, s)] for s in action.slots]


def start():
    with bpy.context.temp_override(area=area, region=region):
        assert bpy.ops.kr.preview_start() == {'FINISHED'}
    return preview.session(ob)


def settle():
    started = time.monotonic()
    ticks = 0
    while preview.session() and preview.session().status in {'WAITING', 'COMPUTING'}:
        preview.tick()
        ticks += 1
        assert time.monotonic()-started < 30, 'Preview timed out'
    s = preview.session()
    assert s and s.status == 'READY', s.error if s else ob.kr_settings.preview_notice
    return s, ticks


def temporaries():
    return [a for a in bpy.data.actions if a.get('_kr_preview_owner')]


original = signature(source)
count = len(bpy.data.actions)
s = start()
check('preview starts without replacing the Action', ob.animation_data.action == source and not preview.ready(ob))
check('timer registered for interactive work', bpy.app.timers.is_registered(preview.tick))
s, ticks = settle()
check('calculation is split across multiple ticks', ticks > 1)
first = signature(s.displayed)
check('completed preview reduces selected keys', s.report.scope_after < s.report.scope_before)
check('source and unrelated slot stay exact', signature(source) == original and first[1] == original[1])
check('unselected bone stays exact', first[0][1] == original[0][1])
check('unselected gap and outward handles stay exact',
      [k for k in first[0][0] if 300 < k['co'][0] < 331] == original[0][0][300:330])
check('ready result enables Apply', bpy.ops.kr.preview_apply.poll())
preview.compare(ob, True)
check('original comparison shows source', ob.animation_data.action == source)
st.preview_amount = 2
check('parameter change disables Apply immediately', not bpy.ops.kr.preview_apply.poll())
s, _ = settle()
check('updates respect Original comparison choice', ob.animation_data.action == source)
preview.compare(ob, False)
check('preview comparison shows latest completed result', ob.animation_data.action == s.displayed)
st.preview_amount = 1
s, _ = settle()
check('A B A returns to identical source-based curves', signature(s.displayed) == first)

# Capture is frozen even if visible bone/key selection changes during preview.
ob.pose.bones['Upper'].select, ob.pose.bones['Other'].select = False, True
st.preview_amount = .5
preview.tick()
st.preview_amount = 4
st.preview_amount = .75
s, _ = settle()
expected = source.copy()
report = reduce_action(expected, expected.slots[0], Settings(method='SIMPLIFY', simplify_mode='FIT',
    strength=.75, selected_bones={'Upper'}, key_selection=s.selection))
check('rapid changes publish only the latest setting', signature(s.displayed) == signature(expected))
check('bone scope stays frozen during slider changes', signature(s.displayed)[0][1] == original[0][1])
bpy.data.actions.remove(expected)
max_tick = s.max_tick
preview.cancel()
check('cancel restores assignment slot and original selection', ob.animation_data.action == source and
      ob.animation_data.action_slot.identifier == identifier and signature(source) == original)
check('cancel restores starting bone selection', ob.pose.bones['Upper'].select and not ob.pose.bones['Other'].select)
check('cancel removes private Actions and timer', not temporaries() and len(bpy.data.actions) == count and
      not bpy.app.timers.is_registered(preview.tick))

for bone in ob.pose.bones:
    bone.select = False
try:
    with bpy.context.temp_override(area=area, region=region):
        preview.start(bpy.context)
except ValueError:
    pass
else:
    raise AssertionError('Empty bones must reject')
check('empty bone filter never creates a whole Action preview', not temporaries() and preview.session() is None)
ob.pose.bones['Upper'].select = True
for fc in slot_curves(source, source.slots[0]):
    for k in fc.keyframe_points:
        k.select_control_point = False
try:
    with bpy.context.temp_override(area=area, region=region):
        preview.start(bpy.context)
except ValueError:
    pass
else:
    raise AssertionError('Empty keys must reject')
check('empty key selection is rejected before making copies', not temporaries() and preview.session() is None)
for fc in slot_curves(source, source.slots[0]):
    for i, k in enumerate(fc.keyframe_points):
        k.select_control_point = i < 300 or i >= 330

s = start()
preview.tick()
preview.cancel()
check('cancelling unfinished work is atomic', signature(source) == original and
      ob.animation_data.action == source and not temporaries())

# Exceptions leave the last valid result visible but cannot be applied.
s = start()
s, _ = settle()
last = s.displayed
real_reduce = preview.reduce_action_steps
def fail(*args, **kwargs):
    yield
    raise RuntimeError('Injected fitting failure')
preview.reduce_action_steps = fail
st.preview_amount = 1.25
while preview.session().status in {'WAITING', 'COMPUTING'}:
    preview.tick()
check('failed calculation keeps previous result and blocks Apply',
      s.status == 'ERROR' and ob.animation_data.action == last and not preview.ready(ob))
preview.reduce_action_steps = real_reduce
st.preview_amount = 1
settle()
check('a new request recovers from a failed calculation', preview.ready(ob))
preview.cancel()

# External Action replacement must never be overwritten by a late job.
s = start()
replacement = source.copy()
addon.assign(ob, replacement, identifier)
preview.tick()
check('external Action assignment stops without overwriting it',
      preview.session() is None and ob.animation_data.action == replacement and not temporaries())
addon.assign(ob, source, identifier)
bpy.data.actions.remove(replacement)

s = start()
other = bpy.data.objects.new('OtherActiveObject', None)
bpy.context.collection.objects.link(other)
bpy.context.view_layer.objects.active = other
preview.tick()
check('object change restores the old object and closes preview',
      preview.session() is None and ob.animation_data.action == source and not temporaries())
bpy.context.view_layer.objects.active = ob
bpy.data.objects.remove(other, do_unlink=True)

s = start()
s, _ = settle()
fc = slot_curves(source, source.slots[0])[0]
fc.keyframe_points[0].co.y += .1
st.preview_amount = 2
while preview.session() and preview.session().status in {'WAITING', 'COMPUTING'}:
    preview.tick()
check('source edit stops stale publication without losing the edit',
      preview.session() is None and abs(fc.keyframe_points[0].co.y-.1) < 1e-6 and not temporaries())
fc.keyframe_points[0].co.y = 0
st.preview_amount = 1

s = start()
s, _ = settle()
edited = s.displayed
slot_curves(edited, edited.slots[0])[0].keyframe_points[0].co.y += .2
preview.cancel()
check('manual edits to a preview are retained instead of deleted',
      ob.animation_data.action == edited and edited.use_fake_user and not edited.get('_kr_preview_owner'))
addon.assign(ob, source, identifier)
bpy.data.actions.remove(edited)

s = start()
s, _ = settle()
shared = s.displayed
other = bpy.data.objects.new('SharedPreviewUser', None)
bpy.context.collection.objects.link(other)
addon.assign(other, shared, identifier)
preview.cancel()
check('shared result is retained and released from temporary ownership',
      other.animation_data.action == shared and not shared.get('_kr_preview_owner') and not temporaries())
bpy.data.objects.remove(other, do_unlink=True)
bpy.data.actions.remove(shared)

s = start()
preview.tick()
preview.shutdown()
check('reload cleanup stops timers and restores the starting Action', preview.session() is None and
      ob.animation_data.action == source and not temporaries() and not bpy.app.timers.is_registered(preview.tick))
preview.register()
preview.register()
check('handler registration is idempotent', all(getattr(bpy.app.handlers, name).count(callback) == 1
      for name, callback in preview._HANDLERS))

with bpy.context.temp_override(area=area, region=region):
    bpy.ops.kr.reduce()
manual_result = st.reduced
manual_mask = st.selection_json
s = start()
s, _ = settle()
preview.cancel()
check('preview cancellation restores a pre-existing manual comparison', addon.current_pair(ob) and
      st.source == source and st.reduced == manual_result and st.selection_json == manual_mask and
      ob.animation_data.action == manual_result)
bpy.ops.kr.cancel()
bpy.data.actions.remove(manual_result)

# Undo snapshots made while sliders are active can contain temporary IDs.
bpy.ops.ed.undo_push(message='Before live preview')
s = start()
settle()
bpy.ops.ed.undo_push(message='Live preview A')
st.preview_amount = 2
settle()
bpy.ops.ed.undo_push(message='Live preview B')
bpy.ops.ed.undo()
ob = bpy.data.objects['PreviewRig']
bpy.context.view_layer.objects.active = ob
source = bpy.data.actions['InteractiveSource']
st = ob.kr_settings
check('undo during a live session restores source and removes restored temporary IDs',
      preview.session() is None and not temporaries() and ob.animation_data.action == source)
bpy.ops.ed.redo()
ob = bpy.data.objects['PreviewRig']
bpy.context.view_layer.objects.active = ob
source = bpy.data.actions['InteractiveSource']
st = ob.kr_settings
check('redo cannot revive an obsolete live session', preview.session() is None and not temporaries() and
      ob.animation_data.action == source)
st.preview_amount = 1

# Apply closes the runtime; one undo returns to the starting Action, redo restores it.
s = start()
s, _ = settle()
applied_shape = signature(s.displayed)
with bpy.context.temp_override(area=area, region=region):
    check('Apply succeeds on the completed current result', bpy.ops.kr.preview_apply() == {'FINISHED'})
applied_name = ob.animation_data.action.name
check('applied Action is editable and no longer automatic', preview.session() is None and
      not temporaries() and signature(ob.animation_data.action) == applied_shape and not addon.current_pair(ob))
bpy.ops.ed.undo_push(message='After Apply Curve Preview')
bpy.ops.ed.undo()
ob = bpy.data.objects['PreviewRig']
bpy.context.view_layer.objects.active = ob
check('one undo restores starting assignment', ob.animation_data.action.name == 'InteractiveSource' and not temporaries())
bpy.ops.ed.redo()
ob = bpy.data.objects['PreviewRig']
bpy.context.view_layer.objects.active = ob
check('redo restores the applied curves', ob.animation_data.action.name == applied_name and signature(ob.animation_data.action) == applied_shape)
source = bpy.data.actions['InteractiveSource']
addon.assign(ob, source, identifier)
st = ob.kr_settings

# Saving cannot persist a half-computed Action or revive an obsolete timer.
s = start()
s, _ = settle()
scratch = output/'interactive_preview.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(scratch), check_existing=False)
check('save cancels an unapplied preview and cleans temporary data',
      preview.session() is None and ob.animation_data.action == source and not temporaries())
bpy.ops.wm.open_mainfile(filepath=str(scratch), load_ui=False)
ob = bpy.data.objects['PreviewRig']
bpy.context.view_layer.objects.active = ob
source = bpy.data.actions['InteractiveSource']
st = ob.kr_settings
check('reopen has no stale preview session or temporary Actions', preview.session() is None and not temporaries())
check('source curves survived lifecycle unchanged', signature(source) == original)

fc = slot_curves(source, source.slots[0])[0]
modifier = fc.modifiers.new('NOISE')
modifier.strength = .1
s = start()
s, _ = settle()
check('modified curves are preserved and reported during preview', bool(s.report.warnings) and
      snapshot(slot_curves(s.displayed, s.displayed.slots[0])[0]) == snapshot(fc))
preview.cancel()
check('source modifier settings survive preview cancellation', len(fc.modifiers) == 1 and
      abs(fc.modifiers[0].strength-.1) < 1e-6)
fc.modifiers.remove(modifier)

qsource = bpy.data.actions.new('QuaternionPreviewSource')
qslot = qsource.slots.new(id_type='OBJECT', name=ob.name)
qbag = qsource.layers.new('Layer').strips.new(type='KEYFRAME').channelbag(qslot, ensure=True)
for axis in range(4):
    qcurve = qbag.fcurves.new('pose.bones["Upper"].rotation_quaternion', index=axis)
    qcurve.keyframe_points.add(181)
    for i, key in enumerate(qcurve.keyframe_points):
        a, b = .4*math.sin(i/31), .3*math.sin(i/17)
        q = math.cos(a)*math.cos(b), math.sin(a)*math.cos(b), math.cos(a)*math.sin(b), math.sin(a)*math.sin(b)
        key.co = (i+1, q[axis])
        key.interpolation = 'BEZIER'
        key.handle_left_type = key.handle_right_type = 'AUTO_CLAMPED'
        key.select_control_point = True
    qcurve.update()
ob.pose.bones['Upper'].rotation_mode = 'QUATERNION'
addon.assign(ob, qsource, qslot.identifier)
s = start()
s, _ = settle()
qinput = slot_curves(qsource, qslot)
qoutput = slot_curves(s.displayed, s.displayed.slots[0])
check('interactive quaternions retain shared WXYZ times', s.report.scope_after < s.report.scope_before and
      len({tuple(k.co.x for k in fc.keyframe_points) for fc in qoutput}) == 1)
check('interactive quaternions satisfy independent orientation checks', max(distance(
    tuple(fc.evaluate(1+i/8) for fc in qinput), tuple(fc.evaluate(1+i/8) for fc in qoutput), 'QUATERNION')
    for i in range(180*8+1)) <= math.radians(.5))
preview.cancel()
check('quaternion cancellation restores exact source assignment', ob.animation_data.action == qsource and not temporaries())
addon.assign(ob, source, identifier)
ob.pose.bones['Upper'].rotation_mode = 'XYZ'
bpy.data.actions.remove(qsource)

print('PREVIEW_TEST_SUMMARY', json.dumps({'passed': True, 'checks': len(checks),
      'version': bpy.app.version_string, 'maximum_tick_seconds': max_tick}), flush=True)
