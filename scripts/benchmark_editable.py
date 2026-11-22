"""Compare working FIT against a supplied local extension ZIP on generated curves.

Blender: --background --factory-startup --offline-mode --python-exit-code 1
--python scripts/benchmark_editable.py -- --baseline dist/keyframe_reducer-1.3.0.zip
--output build/editable-study
Use an isolated BLENDER_USER_RESOURCES directory, as with scripts/run_tests.py.
"""
import argparse
import importlib
import json
import math
from pathlib import Path
import sys
import time
import zipfile

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from curve_cases import bone_cases
from keyframe_reducer import engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    package = output/'kr_study_baseline'
    package.mkdir(exist_ok=True)
    # Load only the numerical modules from our supplied baseline, with a unique
    # package name. Do not register either extension into the user's profile.
    (package/'__init__.py').write_text('')
    with zipfile.ZipFile(args.baseline) as archive:
        for name in ('core', 'fitting', 'engine', 'selection', 'simplify'):
            (package/(name+'.py')).write_bytes(archive.read(name+'.py'))
    sys.path.insert(0, str(output))
    baseline = importlib.import_module('kr_study_baseline.engine')
    results = {}
    path = 'pose.bones["GeneratedBone"].rotation_euler'
    for name, count, function in bone_cases():
        source = bpy.data.actions.new('Study_'+name)
        slot = source.slots.new(id_type='OBJECT', name='GeneratedRig')
        bag = source.layers.new('Layer').strips.new(type='KEYFRAME').channelbag(slot, ensure=True)
        curve = bag.fcurves.new(path, index=0)
        curve.keyframe_points.add(count)
        for i, key in enumerate(curve.keyframe_points):
            key.co = (i+1, function(i))
            key.interpolation = 'BEZIER'
            key.handle_left_type = key.handle_right_type = 'AUTO_CLAMPED'
        curve.update()
        samples = [1+i/8 for i in range((count-1)*8+1)]
        reference = [curve.evaluate(t) for t in samples]
        mask = [dict(data_path=path, array_index=0, frames=list(range(1, count+1)))]
        row = dict(source_keys=count, reference=list(zip(samples, reference)), results={})
        for label, module, degrees in [('1.3', baseline, .5), ('current', engine, .5),
                                        ('fine', engine, .25), ('broad', engine, 1.)]:
            started = time.perf_counter()
            target = source.copy()
            report = module.reduce_action(target, target.slots[0], module.Settings(
                method='SIMPLIFY', simplify_mode='FIT', key_selection=mask,
                rotation_error=math.radians(degrees)))
            elapsed = time.perf_counter()-started
            fitted = engine.slot_curves(target, target.slots[0])[0]
            evaluated = [fitted.evaluate(t) for t in samples]
            error = math.degrees(max(abs(a-b) for a, b in zip(reference, evaluated)))
            assert error <= degrees*1.001, (name, label, error)
            row['results'][label] = dict(keys=report.scope_after, tolerance_degrees=degrees,
                error_degrees=error, seconds=elapsed, controls=engine.snapshot(fitted),
                samples=list(zip(samples, evaluated)))
            bpy.data.actions.remove(target)
        results[name] = row
        print(name, {key: (r['keys'], round(r['error_degrees'], 4), round(r['seconds'], 3))
                     for key, r in row['results'].items()}, flush=True)
        bpy.data.actions.remove(source)
    (output/'comparison.json').write_text(json.dumps(results, indent=2)+'\n')


if __name__ == '__main__':
    main()
