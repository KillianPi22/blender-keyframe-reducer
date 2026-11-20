# Tests

Run `python scripts/run_tests.py --blender /path/to/blender` from the repository root. The runner supports any current working directory and writes to a unique ignored `build/test-runs/` directory. It uses offline Blender background processes and isolated user resources, so tests do not install into the normal profile.

| Suite | Script | Baseline checks |
|---|---|---:|
| core | `tests_blender.py` | 25 |
| selection | `tests_selection.py` | 28 |
| upgrade | `tests_upgrade.py` | 17 |

The core and selection suites import the working source. The upgrade suite intentionally installs original 1.0.0, 1.1.0 and 1.1.1 archives to reproduce the original stale-module bug and verify its fix. Its package-only reload reproducer is necessary even when Blender's native installer refreshes modules in a particular headless run.

Do not rewrite the fixture archives to match development source. The historical 1.1.1 regression does not replace a future test upgrading to a newer release.

## Optional production-scene tests

`test_scene.py` and `test_selection_scene.py` are preserved integration tests for the original private Mixamo fixture. The expected fixture has an `Armature` object and the `Swing` and `DropKick` Actions used by the earlier development session. It is not included in this repository. Do not substitute an arbitrary character and expect the fixture-specific assertions to pass.

```sh
blender --background /local/private/TestImportMixamoAnim1.blend --factory-startup --python-exit-code 1 --python tests/test_scene.py -- /local/scratch/key-reducer-results
blender --background /local/private/TestImportMixamoAnim1.blend --factory-startup --python-exit-code 1 --python tests/test_selection_scene.py
```

The scripts do not overwrite their source scene. For these optional direct invocations, use an isolated Blender profile just as the main runner does. `KR_TEST_OUTPUT` can redirect selection test reports. Generated scenes and logs are not release fixtures.
