"""Upgrade from immutable 1.1.1 to working source in an isolated profile."""
import importlib
import json
import os
from pathlib import Path
import sys
import tomllib

import bpy

root = Path(__file__).resolve().parents[1]
profile = Path(os.environ['KR_TEST_PROFILE']).resolve()
output = Path(os.environ['KR_TEST_OUTPUT']).resolve()
assert profile.is_relative_to(root/'build')
repo = next(r for r in bpy.context.preferences.extensions.repos if r.module == 'user_default')
assert Path(repo.directory).resolve().is_relative_to(profile)
sys.path.insert(0, str(root/'scripts'))
import build_release

version = build_release.package_version()
archive = output/f'keyframe_reducer-{version}.zip'
entries = {p.relative_to(build_release.PACKAGE).as_posix(): p.read_bytes()
           for p in build_release.PACKAGE.rglob('*') if p.is_file()
           and '__pycache__' not in p.parts and p.suffix != '.pyc'}
build_release.write_zip(archive, entries)
module_name = 'bl_ext.user_default.keyframe_reducer'
checks = []


def check(name, condition):
    assert condition, name
    checks.append(name)
    print('PASS', name, flush=True)


def install(path):
    assert bpy.ops.extensions.package_install_files(filepath=str(path), repo='user_default',
        enable_on_install=True, overwrite=True) == {'FINISHED'}
    return sys.modules[module_name]


addon = install(root/'tests/fixtures/releases/keyframe_reducer-1.1.1.zip')
old_settings = addon.Settings
ob = bpy.data.objects.new('CurrentUpgrade', None)
bpy.context.collection.objects.link(ob)
for other in bpy.context.selected_objects:
    other.select_set(False)
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
source = bpy.data.actions.new('UpgradeSource')
slot = source.slots.new(id_type='OBJECT', name=ob.name)
bag = source.layers.new('Layer').strips.new(type='KEYFRAME').channelbag(slot, ensure=True)
fc = bag.fcurves.new('location', index=0)
for frame in range(1, 32):
    key = fc.keyframe_points.insert(frame, frame/10)
    key.interpolation = 'LINEAR'
    key.select_control_point = 6 <= frame <= 24
    key.select_left_handle = key.select_right_handle = False
addon.assign(ob, source, slot.identifier)
area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
area.type = 'GRAPH_EDITOR'
area.spaces.active.mode = 'FCURVES'
region = next(r for r in area.regions if r.type == 'UI')
ob.kr_settings.scope = 'KEYS'
ob.kr_settings.interpolation = 'LINEAR'
with bpy.context.temp_override(area=area, region=region):
    check('baseline comparison created', bpy.ops.kr.reduce() == {'FINISHED'})
mask = ob.kr_settings.selection_json
engine = sys.modules[module_name+'.engine']
source_keys = engine.snapshot(fc)

# Model a package-only updater which leaves the old numerical modules cached.
addon.unregister()
package_dir = Path(addon.__file__).parent.resolve()
assert package_dir.is_relative_to(profile)
for name, data in entries.items():
    destination = package_dir/name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
importlib.invalidate_caches()
addon = importlib.reload(addon)
addon.register()
st = ob.kr_settings
check('working Settings replaces stale baseline module', addon.Settings is not old_settings and
      addon.Settings(method='SIMPLIFY').method == 'SIMPLIFY')
check('old files default to Key Reducer', st.method == 'REDUCE')
check('baseline comparison and selection survive upgrade', st.source == source and st.selection_json == mask)
st.method = 'SIMPLIFY'
check('simplify runs after package-only upgrade', bpy.ops.kr.reduce() == {'FINISHED'} and st.after < st.before)
check('simplify retains original comparison source', st.source == source and st.selection_json == mask)
first = [engine.snapshot(c) for c in addon.slot_curves(st.reduced, st.reduced.slots[0])]

# Then exercise the real extension installer over an enabled 1.1.1 instance.
addon = install(root/'tests/fixtures/releases/keyframe_reducer-1.1.1.zip')
check('baseline re-enabled for native upgrade', 'method' not in addon.Settings.__dataclass_fields__)
addon = install(archive)
st = ob.kr_settings
st.method = 'SIMPLIFY'
check('native installer loads current version',
      tomllib.loads(Path(addon.__file__).with_name('blender_manifest.toml').read_text())['version'] == version)
check('native upgrade recalculates from source', bpy.ops.kr.reduce() == {'FINISHED'} and st.source == source)
engine = sys.modules[module_name+'.engine']
simplify = sys.modules[module_name+'.simplify']
check('simplify imports refreshed helpers', simplify.snapshot is engine.snapshot and
      simplify.selected_runs is sys.modules[module_name+'.selection'].selected_runs)
check('native and package-only upgrades yield identical output', first ==
      [engine.snapshot(c) for c in addon.slot_curves(st.reduced, st.reduced.slots[0])])
check('upgrade leaves source metadata intact', engine.snapshot(fc) == source_keys)
check('old comparison defaults to existing-handle simplification', st.simplify_mode == 'KEEP')
st.simplify_mode = 'FIT'
check('editable Bezier runs after native upgrade', bpy.ops.kr.reduce() == {'FINISHED'} and st.source == source)
fitting = sys.modules[module_name+'.fitting']
check('fitting dependencies are refreshed in order', simplify.fit_bezier is fitting.fit_bezier and
      fitting.distance is sys.modules[module_name+'.core'].distance)
print('CURRENT_UPGRADE_TEST_SUMMARY', json.dumps({'passed': True, 'checks': len(checks),
      'version': bpy.app.version_string, 'addon_version': version}), flush=True)
