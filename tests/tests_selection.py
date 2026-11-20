"""Blender 5.2 integration tests for strict partial key reduction."""
import sys
import os
import math
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
import keyframe_reducer as addon
TEST_OUTPUT = Path(os.environ.get('KR_TEST_OUTPUT', Path(__file__).resolve().parents[1]/'build/test-output'))
TEST_OUTPUT.mkdir(parents=True, exist_ok=True)
from keyframe_reducer.engine import Settings, snapshot, slot_curves, reduce_action
from keyframe_reducer.core import distance

addon.register()
passed = []


def check(name, condition):
    assert condition, name
    passed.append(name)
    print('PASS',name,flush=True)


def new_action(name):
    action = bpy.data.actions.new(name)
    slot = action.slots.new(id_type='OBJECT',name=ob.name)
    layer = action.layers.new('Layer')
    strip = layer.strips.new(type='KEYFRAME')
    return action, slot, strip.channelbag(slot,ensure=True)


def add_curve(bag,path,axis,values):
    fc = bag.fcurves.new(path,index=axis)
    fc.auto_smoothing = 'CONT_ACCEL'
    for frame,value in enumerate(values,1):
        key = fc.keyframe_points.insert(frame,value)
        key.interpolation = 'BEZIER'
        key.handle_left_type = key.handle_right_type = 'AUTO_CLAMPED'
        key.select_control_point = key.select_left_handle = key.select_right_handle = False
    fc.update()
    return fc


def select(curves, mapping):
    for fc in curves:
        frames = mapping.get((fc.data_path,fc.array_index),set())
        for key in fc.keyframe_points:
            key.select_control_point = key.co.x in frames
            key.select_left_handle = key.select_right_handle = False


def capture(curves):
    return [{'data_path':fc.data_path,'array_index':fc.array_index,
             'frames':[float(k.co.x) for k in fc.keyframe_points if k.select_control_point]}
            for fc in curves if any(k.select_control_point for k in fc.keyframe_points)]


def curve(action,path,axis):
    return next(fc for fc in slot_curves(action,action.slots[0]) if fc.data_path==path and fc.array_index==axis)


ob = bpy.data.objects.new('SelectionTest',None)
bpy.context.collection.objects.link(ob)
bpy.context.view_layer.objects.active = ob
for other in bpy.context.selected_objects:
    other.select_set(False)
ob.select_set(True)
source,slot,bag = new_action('SelectedSource')
for axis in range(3):
    add_curve(bag,'location',axis,[i/10 + math.sin(i/8)*(axis+1)*.04 for i in range(101)])
for axis in range(4):
    add_curve(bag,'rotation_quaternion',axis,[math.cos(i/80) if axis==0 else
                math.sin(i/80) if axis==3 else 0 for i in range(101)])
curves = slot_curves(source,slot)
selected = set(range(11,32)) | set(range(51,72)) | {91}
select(curves,{('location',0):selected})
originals = {(fc.data_path,fc.array_index):snapshot(fc) for fc in curves}
settings = Settings(position_error=.02, sample_step=.25,key_selection=capture(curves))
result = source.copy()
report = reduce_action(result,result.slots[0],settings)
check('selected X actually reduced', report.after < report.before)
check('source entirely unchanged', all(snapshot(fc)==originals[(fc.data_path,fc.array_index)] for fc in curves))
x = curve(result,'location',0)
check('unselected X keys exactly preserved', [k for k in snapshot(x) if k['co'][0] not in selected] ==
      [k for k in originals[('location',0)] if k['co'][0] not in selected])
check('Y Z and quaternion untouched', all(snapshot(fc)==originals[(fc.data_path,fc.array_index)]
      for fc in slot_curves(result,result.slots[0]) if (fc.data_path,fc.array_index)!=('location',0)))
kept = {k.co.x for k in x.keyframe_points}
check('selection boundaries and isolated key retained', {11,31,51,71,91}.issubset(kept))
check('no bridge over unselected gaps', set(range(32,51)).issubset(kept))
outside_error,inside_error = 0.0,0.0
for i in range(401):
    frame = 1+i*.25
    err = abs(x.evaluate(frame)-curves[0].evaluate(frame))
    if 11<=frame<=31 or 51<=frame<=71:
        inside_error = max(inside_error,err)
    else:
        outside_error = max(outside_error,err)
check('outside motion identical including subframes', outside_error < 1e-7)
check('inside selection within tolerance', inside_error <= settings.position_error*1.0001)
check('surviving selected points remain selected', all(k.select_control_point for k in x.keyframe_points if k.co.x in selected))

# Same source with partially selected quaternion: do not silently edit siblings.
select(curves,{('rotation_quaternion',0):set(range(21,61))})
partial = source.copy()
partial_before = [snapshot(fc) for fc in slot_curves(partial,partial.slots[0])]
report = reduce_action(partial,partial.slots[0],Settings(key_selection=capture(curves)))
check('partial quaternion selection preserved', partial_before == [snapshot(fc) for fc in slot_curves(partial,partial.slots[0])])
check('quaternion instruction reported', any('Quaternion' in s for s in report.warnings))

select(curves,{('rotation_quaternion',i):set(range(21,61)) for i in range(4)})
full = source.copy()
settings_q = Settings(key_selection=capture(curves),sample_step=.25)
report = reduce_action(full,full.slots[0],settings_q)
check('complete quaternion selection reduced', report.after < report.before)
q_src = [curve(source,'rotation_quaternion',i) for i in range(4)]
q_dst = [curve(full,'rotation_quaternion',i) for i in range(4)]
check('quaternion component key times aligned', len({tuple(k.co.x for k in fc.keyframe_points) for fc in q_dst})==1)
check('quaternion outside keys unchanged', all(
      [k for k in snapshot(a) if not 21<=k['co'][0]<=60] == [k for k in snapshot(b) if not 21<=k['co'][0]<=60]
      for a,b in zip(q_src,q_dst)))
max_angle = max(distance(tuple(fc.evaluate(1+i*.25) for fc in q_src),
                         tuple(fc.evaluate(1+i*.25) for fc in q_dst),'QUATERNION') for i in range(401))
check('quaternion orientation tolerance checked independently', max_angle <= settings_q.rotation_error*1.0001)

# Three selected linear keys can reduce to their endpoints.
small,ss,sb = new_action('ThreeKeys')
fc = add_curve(sb,'location',0,[float(i) for i in range(8)])
for k in fc.keyframe_points: k.interpolation='LINEAR'
select([fc],{('location',0):{3,4,5}})
rr = reduce_action(small,ss,Settings(interpolation='LINEAR',key_selection=capture([fc])))
check('three-key selection supported', rr.before-rr.after == 1 and {3,5}.issubset({k.co.x for k in fc.keyframe_points}))

# Real Graph Editor context: hidden curves must not leak stale selections.
addon.assign(ob,source,slot.identifier)
select(curves,{('location',0):selected,('location',1):set(range(1,102))})
curve(source,'location',1).hide = True
area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
area.type = 'GRAPH_EDITOR'
area.spaces.active.mode = 'FCURVES'
area.spaces.active.dopesheet.show_only_selected = True
region = next(r for r in area.regions if r.type == 'WINDOW')
ui_region = next(r for r in area.regions if r.type == 'UI')
with bpy.context.temp_override(area=area,region=ui_region):
    mask = addon.capture_key_selection(bpy.context,source,slot)
    check('sidebar UI region captures the visible selection', len(mask)==1 and mask[0]['array_index']==0)
with bpy.context.temp_override(area=area,region=region):
    mask = addon.capture_key_selection(bpy.context,source,slot)
    check('hidden channel excluded from visible selection', len(mask)==1 and mask[0]['array_index']==0)
    st = ob.kr_settings
    st.scope = 'KEYS'
    st.position_error = .02
    st.dense_check = True
    check('selected-key operator works in Graph Editor', bpy.ops.kr.reduce()=={'FINISHED'})
    mask_saved = st.selection_json
    first_source = st.source
    select(slot_curves(st.reduced,st.reduced.slots[0]),{})
    st.strength = 2
    check('recalculate retains captured selection', bpy.ops.kr.reduce()=={'FINISHED'} and
          st.selection_json==mask_saved and st.source==first_source)
    previous = st.reduced
    previous_x = snapshot(curve(previous,'location',0))
    select(slot_curves(previous,previous.slots[0]),{('location',0):set(range(36,47))})
    check('new-selection operator', bpy.ops.kr.reduce(new_selection=True)=={'FINISHED'})
    check('new selection rebases on displayed result', st.source==previous)
    new_x = snapshot(curve(st.reduced,'location',0))
    check('new selection keeps earlier reductions',
          [(k['co'],k['left'],k['right']) for k in new_x if k['co'][0]<36 or k['co'][0]>46] ==
          [(k['co'],k['left'],k['right']) for k in previous_x if k['co'][0]<36 or k['co'][0]>46])
    select(slot_curves(st.reduced,st.reduced.slots[0]),{})
    old_action, count = ob.animation_data.action,len(bpy.data.actions)
    try: addon.run_reduction(bpy.context,new_selection=True)
    except ValueError: pass
    else: raise AssertionError('empty selection must reject')
    check('empty selection never reduces full Action', ob.animation_data.action==old_action and len(bpy.data.actions)==count)

# Save/reload: exact outside handles and captured selection must survive.
scratch = TEST_OUTPUT/'selection_test.blend'
stored_action_name = ob.animation_data.action.name
stored = [snapshot(fc) for fc in slot_curves(ob.animation_data.action,ob.animation_data.action_slot)]
saved_mask = ob.kr_settings.selection_json
bpy.ops.wm.save_as_mainfile(filepath=str(scratch),check_existing=False)
bpy.ops.wm.open_mainfile(filepath=str(scratch),load_ui=False)
ob = bpy.data.objects['SelectionTest']
bpy.context.view_layer.objects.active = ob
check('selection persisted after reopen', ob.kr_settings.selection_json==saved_mask)
check('all curve metadata persisted after reopen', stored ==
      [snapshot(fc) for fc in slot_curves(ob.animation_data.action,ob.animation_data.action_slot)])
check('comparison works after reopen', bpy.ops.kr.compare(reduced=False)=={'FINISHED'} and bpy.ops.kr.compare(reduced=True)=={'FINISHED'})
old_count = ob.kr_settings.after
check('recalculate persisted selection', bpy.ops.kr.reduce()=={'FINISHED'} and ob.kr_settings.after==old_count)

summary = {'version':bpy.app.version_string,'checks':len(passed),'passed':True,
           'tests':passed,'outside_max_error':outside_error,'inside_max_error':inside_error,
           'quaternion_max_error_radians':max_angle}
(TEST_OUTPUT/'selection_test_report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print('SELECTION_TEST_SUMMARY',json.dumps(summary),flush=True)
