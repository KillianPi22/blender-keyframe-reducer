"""Selected-key reduction on the supplied Mixamo scene; never saves it."""
import sys
import os
import json
import math
from dataclasses import asdict
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import keyframe_reducer as addon
TEST_OUTPUT = Path(os.environ.get('KR_TEST_OUTPUT', Path(__file__).resolve().parents[1]/'build/test-output'))
TEST_OUTPUT.mkdir(parents=True, exist_ok=True)
from keyframe_reducer.engine import slot_curves, snapshot

addon.register()
ob = bpy.data.objects['Armature']
if bpy.context.object and bpy.context.object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
source = bpy.data.actions['Swing']
addon.assign(ob,source,source.slots[0].identifier)
ob.animation_data.use_nla = False
curves = slot_curves(source,source.slots[0])
bones = [b.name for b in ob.data.bones if b.name.endswith(('Hips','LeftForeArm'))]
assert len(bones)==2,bones
paths = {ob.pose.bones[name].path_from_id(prop) for name in bones
         for prop in ('location','rotation_quaternion','scale')}
selected = set(range(11,32)) | set(range(44,65))
for fc in curves:
    fc.hide = False
    for key in fc.keyframe_points:
        key.select_control_point = fc.data_path in paths and key.co.x in selected
        key.select_left_handle = key.select_right_handle = False
originals = {(fc.data_path,fc.array_index):snapshot(fc) for fc in curves}
outside_frames = [1+i*.25 for i in range(293)
                  if not (11<=1+i*.25<=31 or 44<=1+i*.25<=64)]

def poses():
    output = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for frame in outside_frames:
        bpy.context.scene.frame_set(int(frame),subframe=frame-int(frame))
        evaluated = ob.evaluated_get(depsgraph)
        output.append([tuple(evaluated.matrix_world @ bone.tail) for bone in evaluated.pose.bones])
    return output

baseline = poses()
area = next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
area.type = 'GRAPH_EDITOR'
area.spaces.active.mode = 'FCURVES'
area.spaces.active.dopesheet.show_only_selected = False
region = next(r for r in area.regions if r.type=='UI')
state = ob.kr_settings
state.scope = 'KEYS'
state.dense_check = True
with bpy.context.temp_override(area=area,region=region):
    report = addon.run_reduction(bpy.context)
assert report.after < report.before,report
assert all(snapshot(fc)==originals[(fc.data_path,fc.array_index)] for fc in curves)
for fc in slot_curves(state.reduced,ob.animation_data.action_slot):
    before = originals[(fc.data_path,fc.array_index)]
    after = snapshot(fc)
    if fc.data_path not in paths:
        assert before==after,fc.data_path
    else:
        assert [k for k in before if k['co'][0] not in selected] == [k for k in after if k['co'][0] not in selected]
        old_times = {k['co'][0] for k in before}
        new_times = {k['co'][0] for k in after}
        assert {11,31,44,64}.issubset(new_times)
        assert new_times.issubset(old_times)
outside = poses()
max_world = max(math.dist(a,b) for aa,bb in zip(baseline,outside) for a,b in zip(aa,bb))
assert max_world < 1e-7,max_world
assert report.max_error_ratio <= 1.0001,report
summary = {'blender':bpy.app.version_string,'passed':True,'action':source.name,
           'selected_bones':bones,'selected_intervals':[[11,31],[44,64]],
           'unselected_keys_exactly_preserved':True,'unselected_channels_exactly_preserved':True,
           'original_action_unchanged':True,'outside_max_world_error':max_world,
           'outside_pose_samples':len(outside_frames),'reduction':asdict(report)}
(TEST_OUTPUT/'selection_scene_report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print('SELECTION_SCENE_OK',json.dumps(summary),flush=True)
