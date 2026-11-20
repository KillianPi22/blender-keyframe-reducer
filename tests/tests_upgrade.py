"""Test native updates and package-only reloads in an isolated Blender profile."""
import sys
import os
import json
import importlib
import tomllib
import zipfile
from pathlib import Path
import bpy

root = Path(__file__).resolve().parents[1]
fixtures = root/'tests/fixtures/releases'
profile = Path(os.environ['KR_TEST_PROFILE']).resolve()
assert profile.is_relative_to(root/'build'), 'Use scripts/run_tests.py for isolated profiles'
output = Path(os.environ['KR_TEST_OUTPUT']).resolve()
output.mkdir(parents=True, exist_ok=True)
module_name = 'bl_ext.user_default.keyframe_reducer'
repo = next(r for r in bpy.context.preferences.extensions.repos if r.module=='user_default')
assert Path(repo.directory).resolve().is_relative_to(profile)
checks = []

def check(name, expression):
    assert expression,name
    checks.append(name)
    print('PASS',name,flush=True)

def install(version):
    archive = fixtures/f'keyframe_reducer-{version}.zip'
    assert bpy.ops.extensions.package_install_files(filepath=str(archive),repo='user_default',
        enable_on_install=True,overwrite=True)=={'FINISHED'}
    module = sys.modules[module_name]
    manifest = Path(module.__file__).with_name('blender_manifest.toml')
    assert tomllib.loads(manifest.read_text(encoding='utf-8'))['version']==version
    return module

def reload_package_only(version):
    """Simulate an updater reloading the entry point but leaving child modules cached.

    Native headless installation can refresh child modules itself, so explicitly
    exercise the stale-cache state reported by the user as well as native updates.
    """
    module = sys.modules[module_name]
    module.unregister()
    package_dir = Path(module.__file__).parent.resolve()
    assert package_dir.is_relative_to(profile)
    with zipfile.ZipFile(fixtures/f'keyframe_reducer-{version}.zip') as archive:
        assert archive.testzip() is None
        for member in archive.infolist():
            assert (package_dir/member.filename).resolve().is_relative_to(package_dir)
        archive.extractall(package_dir)
    importlib.invalidate_caches()
    module = importlib.reload(module)
    module.register()
    return module

addon = install('1.0.0')
old_settings = addon.Settings
check('v1.0 engine loaded', 'key_selection' not in old_settings.__dataclass_fields__)
addon = reload_package_only('1.1.0')
check('v1.1 interface loaded', addon.KR_Settings.bl_rna.properties['scope'].enum_items['KEYS'].name=='Selected Keys')
try:
    addon.Settings(key_selection=[])
except TypeError as error:
    check('reported update bug reproduced', 'unexpected keyword argument' in str(error) and 'key_selection' in str(error))
else:
    raise AssertionError('Expected the original package-only reload bug')
if '--reproduce-only' in sys.argv:
    print('UPGRADE_BUG_REPRODUCED',flush=True)
    sys.exit(0)

addon = reload_package_only('1.1.1')
check('v1.1.1 refreshes cached Settings', addon.Settings is not old_settings and addon.Settings(key_selection=[]).key_selection==[])
engine = sys.modules[module_name+'.engine']
check('entry point uses refreshed engine', addon.reduce_action is engine.reduce_action)

ob = bpy.data.objects.new('UpgradeSelection',None)
bpy.context.collection.objects.link(ob)
for other in bpy.context.selected_objects:
    other.select_set(False)
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
source = bpy.data.actions.new('UpgradeSource')
slot = source.slots.new(id_type='OBJECT',name=ob.name)
bag = source.layers.new('Layer').strips.new(type='KEYFRAME').channelbag(slot,ensure=True)
fc = bag.fcurves.new('location',index=0)
for frame in range(1,32):
    key = fc.keyframe_points.insert(frame,frame/10)
    key.interpolation = 'LINEAR'
    key.select_control_point = 6<=frame<=24
    key.select_left_handle = key.select_right_handle = False
original = engine.snapshot(fc)
addon.assign(ob,source,slot.identifier)
area = next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
area.type = 'GRAPH_EDITOR'
area.spaces.active.mode = 'FCURVES'
region = next(r for r in area.regions if r.type=='UI')
ob.kr_settings.scope = 'KEYS'
ob.kr_settings.interpolation = 'LINEAR'
with bpy.context.temp_override(area=area,region=region):
    check('selected-key operator works after update', bpy.ops.kr.reduce()=={'FINISHED'})
check('selection is reduced', ob.kr_settings.after < ob.kr_settings.before)
check('source remains unchanged', engine.snapshot(fc)==original)
reduced = engine.slot_curves(ob.kr_settings.reduced,ob.animation_data.action_slot)[0]
check('outside keys survive update and reduction',
    [k for k in engine.snapshot(reduced) if not 6<=k['co'][0]<=24] ==
    [k for k in original if not 6<=k['co'][0]<=24])
saved_source = ob.kr_settings.source
saved_mask = ob.kr_settings.selection_json
old_after = ob.kr_settings.after
old_selection_function = sys.modules[module_name+'.selection'].write_group
addon = reload_package_only('1.1.1')
engine = sys.modules[module_name+'.engine']
selection = sys.modules[module_name+'.selection']
check('loaded selection module refreshed in dependency order',
      selection.write_group is engine.write_group and selection.write_group is not old_selection_function)
check('comparison and captured selection survive reinstallation',
      ob.kr_settings.source==saved_source and ob.kr_settings.selection_json==saved_mask)
check('recalculate after warm reinstallation', bpy.ops.kr.reduce()=={'FINISHED'} and ob.kr_settings.after==old_after)
check('compare original after reinstallation', bpy.ops.kr.compare(reduced=False)=={'FINISHED'} and ob.animation_data.action==saved_source)
check('compare reduced after reinstallation', bpy.ops.kr.compare(reduced=True)=={'FINISHED'})

# Also validate Blender's native installer, without restarting this process.
addon = install('1.0.0')
check('native old version enabled', 'key_selection' not in addon.Settings.__dataclass_fields__)
addon = install('1.1.1')
check('native in-session update loads selected-key Settings', addon.Settings(key_selection=[]).key_selection==[])
check('native in-session update keeps working comparison', bpy.ops.kr.reduce()=={'FINISHED'} and ob.kr_settings.after==old_after)

summary = {'blender':bpy.app.version_string,'addon_version':'1.1.1','passed':True,
           'checks':len(checks),'tests':checks,'isolated_preferences':True,
           'original_bug_reproduced':True,'reproduction_method':'package-only reload with old engine cached',
           'native_in_session_update_verified':True,'restart_required_for_fix':False}
(output/'upgrade_test_report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print('UPGRADE_TEST_SUMMARY',json.dumps(summary),flush=True)
