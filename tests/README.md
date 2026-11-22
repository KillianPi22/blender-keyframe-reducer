# Tests

Run `python scripts/run_tests.py --blender /path/to/blender` from the repository root. The runner supports any current working directory and writes to a unique ignored `build/test-runs/` directory. It uses offline Blender background processes and isolated user resources, so tests do not install into the normal profile.

| Suite | Script | Baseline checks |
|---|---|---:|
| core | `tests_blender.py` | 25 |
| selection | `tests_selection.py` | 28 |
| simplify | `tests_simplify.py` | 43 |
| fitting | `tests_fitting.py` | 80 |
| preview | `tests_preview.py` | 45 |
| upgrade | `tests_upgrade.py` | 17 |
| upgrade_current | `tests_upgrade_current.py` | 15 |

The core and selection suites import the working source. The upgrade suite intentionally installs original 1.0.0, 1.1.0 and 1.1.1 archives to reproduce the original stale-module bug and verify its fix. Its package-only reload reproducer is necessary even when Blender's native installer refreshes modules in a particular headless run.

Do not rewrite the fixture archives to match development source. The historical 1.1.1 regression does not replace a future test upgrading to a newer release.

`upgrade_current` creates a temporary archive from the working source under the
isolated test output, then upgrades an enabled historical 1.1.1 installation. It
covers both package-only reload with cached modules and Blender's native extension
installer, including existing comparison and selection state. It never writes a
new historical release fixture.

`fitting` generates a two-bone skeleton and dense rotation curves. It compares
the legacy method and Editable Bezier at identical tolerances, independently
checks eighth-frame errors and the generated child-bone trajectory, and covers
selection boundaries, tangents, Euler turns, complete quaternions, unsupported
curves, pose-bone filtering, undo/redo and reopen. Its output includes
`fit_comparison.json` for plotting and a generated `editable_bone_curves.blend`.
This is not validation against a private production character.
The suite also checks anchor removal/consolidation, holds, small and large
oscillations, weighted source curves, brief gestures, profile setup and stale
result feedback. Independent sixteenth-frame checks catch narrow error peaks.

`preview` exercises the actual cooperative timer callback with real Action data:
latest-request wins, immutable-source A/B/A, frozen bone/key scope, comparison,
pending/error Apply guards, Cancel, external changes, shared/edited results,
undo/redo, save/reopen and reload cleanup. It also covers empty scopes, full
quaternions and unsupported modifiers. It uses no worker threads or sleeps.

`scripts/benchmark_editable.py` compares a supplied historical development ZIP
with the working engine on the generated cases in `curve_cases.py`, at 0.25°,
0.5° and 1°. It writes timings, counts, curves and errors for plotting to the
chosen build output. It does not use the user's Minotaur data or register add-ons.

## Optional production-scene tests

`test_scene.py` and `test_selection_scene.py` are preserved integration tests for the original private Mixamo fixture. The expected fixture has an `Armature` object and the `Swing` and `DropKick` Actions used by the earlier development session. It is not included in this repository. Do not substitute an arbitrary character and expect the fixture-specific assertions to pass.

```sh
blender --background /local/private/TestImportMixamoAnim1.blend --factory-startup --python-exit-code 1 --python tests/test_scene.py -- /local/scratch/key-reducer-results
blender --background /local/private/TestImportMixamoAnim1.blend --factory-startup --python-exit-code 1 --python tests/test_selection_scene.py
```

The scripts do not overwrite their source scene. For these optional direct invocations, use an isolated Blender profile just as the main runner does. `KR_TEST_OUTPUT` can redirect selection test reports. Generated scenes and logs are not release fixtures.
