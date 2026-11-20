"""Integration test on the supplied scene, never saves over its source file."""
import sys
import math
import json
from dataclasses import asdict
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import keyframe_reducer as addon
from keyframe_reducer.engine import Settings, slot_curves, snapshot, reduce_action

addon.register()
out = Path(sys.argv[sys.argv.index('--')+1]) if '--' in sys.argv else Path(__file__).resolve().parents[1]/'build/scene-test'
out.mkdir(parents=True, exist_ok=True)
ob = bpy.data.objects['Armature']
if bpy.context.object and bpy.context.object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
scene = bpy.context.scene
original_action = ob.animation_data.action
original_slot = ob.animation_data.action_slot.identifier
original_nla = ob.animation_data.use_nla
settings = Settings(sample_step=0.25)
report = {'blender': bpy.app.version_string, 'source_file': bpy.data.filepath, 'actions': []}


def signature(a):
    return [(s.identifier, [(c.data_path, c.array_index, snapshot(c)) for c in slot_curves(a,s)]) for s in a.slots]


def poses(start, end, step=1.0):
    output = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for i in range(round((end-start)/step)+1):
        t = start+i*step
        scene.frame_set(int(t), subframe=t-int(t))
        evaluated = ob.evaluated_get(depsgraph)
        output.append({bone.name: (tuple(evaluated.matrix_world @ bone.head),
                                   tuple(evaluated.matrix_world @ bone.tail)) for bone in evaluated.pose.bones})
    return output


def compare_poses(a,b):
    maximum, worst_bone, sample = 0.0, '', 0
    extremities = 0.0
    for i, (aa,bb) in enumerate(zip(a,b)):
        for name in aa:
            for p,q in zip(aa[name],bb[name]):
                err = math.sqrt(sum((x-y)**2 for x,y in zip(p,q)))
                if err > maximum: maximum, worst_bone, sample = err, name, i
                if any(term in name.lower() for term in ('foot','toe','hand')):
                    extremities = max(extremities,err)
    return {'max_world_error': maximum, 'worst_bone': worst_bone,
            'sample_index': sample, 'extremities_max_world_error': extremities}


for name in ('Swing','DropKick','Action'):
    src = bpy.data.actions[name]
    saved = signature(src)
    ob.animation_data.use_nla = False
    addon.assign(ob, src, src.slots[0].identifier)
    start, end = map(int, src.frame_range)
    baseline = poses(start,end,0.5)
    reduced = src.copy()
    reduced.name = name+'_integration'
    stats = reduce_action(reduced,reduced.slots[0],settings)
    addon.assign(ob,reduced,reduced.slots[0].identifier)
    comparison = compare_poses(baseline, poses(start,end,0.5))
    assert signature(src) == saved
    assert stats.after <= stats.before
    assert stats.max_error_ratio <= 1.0001
    report['actions'].append(dict(name=name, **asdict(stats), **comparison))
    print('ACTION_RESULT', json.dumps(report['actions'][-1]), flush=True)
    addon.assign(ob,src,src.slots[0].identifier)
    bpy.data.actions.remove(reduced)

# Bake the visible assembled motion, including the active Action and NLA stack.
addon.assign(ob,original_action,original_slot)
ob.animation_data.use_nla = original_nla
baseline = poses(scene.frame_start,scene.frame_end)
original_action.use_fake_user = True
result = bpy.ops.nla.bake(frame_start=scene.frame_start,frame_end=scene.frame_end,
    step=1,only_selected=False,visual_keying=True,clear_constraints=False,
    clear_parents=False,use_current_action=False,clean_curves=False,
    bake_types={'POSE','OBJECT'},channel_types={'LOCATION','ROTATION','SCALE'})
assert result == {'FINISHED'}
baked = ob.animation_data.action
baked.name = 'KR_Montage_Source'
baked.use_fake_user = True
ob.animation_data.use_nla = False
after_bake = poses(scene.frame_start,scene.frame_end)
report['bake_validation'] = compare_poses(baseline,after_bake)
assert report['bake_validation']['max_world_error'] < 0.0001, report['bake_validation']
state = ob.kr_settings
state.dense_check = True
state.position_error = 0.1
state.rotation_error = math.radians(0.5)
state.scale_error = 0.001
saved = signature(baked)
assert bpy.ops.kr.reduce() == {'FINISHED'}
assert signature(baked) == saved
report['montage'] = json.loads(state.reduced['kr_report'])
report['montage'].update(compare_poses(after_bake,poses(scene.frame_start,scene.frame_end)))
report['scene_unit_scale'] = scene.unit_settings.scale_length
report['armature_scale'] = list(ob.scale)
print('MONTAGE_RESULT', json.dumps(report['montage']), flush=True)
assert bpy.ops.kr.compare(reduced=False) == {'FINISHED'}
assert ob.animation_data.action == baked
assert bpy.ops.kr.compare(reduced=True) == {'FINISHED'}
scene.frame_set(65)
# Save only a new file in the task workspace, keeping the comparison pair.
demo = out/'TestImportMixamoAnim1_KeyReducer.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(demo), check_existing=False)
report['demo'] = str(demo)
(out/'Keyframe_Reducer_Test_Report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('INTEGRATION_OK', flush=True)
