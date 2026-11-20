# Blender Keyframe Reducer

An independent, free Blender extension for reducing animation keys on a protected Action copy. Maintained by Killian Pichon. GPL-3.0-or-later.

**Current baseline: 1.1.1. Requires Blender 5.2.0 or later; tested on Blender 5.2.1 LTS.**

This repository separates add-on development from the portfolio website and the Marionette Workflow Helper. The goal is an efficient animation cleanup workflow inspired by the usability of Maya and Cinema 4D. Feature parity is a development objective, not a claim about this release.

## Available now

- Reduce the active Action or selected, visible Graph Editor key runs.
- Preserve the original Action; compare Original / Reduced and recalculate from the source.
- Group XYZ transforms and complete WXYZ quaternions with sampled error checks.
- Protect significant extrema, marked keys and selected-run boundaries.
- Preserve unselected keys and handles, unrelated slots and unsupported channels.
- English interface; [English guide](keyframe_reducer/README_EN.md) and [French guide](keyframe_reducer/README_FR.md).

**Interactive slider preview is the next milestone. It is not implemented in 1.1.1.** The current interface requires **Recalculate from Source** after changing values. See [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for scope and acceptance criteria.

## Install

Build the extension ZIP, or use the published release when available. In Blender choose **Edit > Preferences > Add-ons > Install from Disk**, select `keyframe_reducer-1.1.1.zip`, and enable the extension. In the Graph Editor press **N > Key Reducer**. Install the inner extension ZIP, not the complete delivery pack.

## Develop and validate

Use Python 3.11 or later for the packaging and runner scripts. Blender's bundled Python also works. No third-party Python dependencies are needed.

```sh
python scripts/build_release.py
python scripts/run_tests.py --blender /path/to/blender
```

On Windows PowerShell:

```powershell
python scripts/run_tests.py --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
```

`BLENDER_BIN` can supply the executable instead. The runner starts separate offline background Blender processes with isolated preferences/extensions. It does not change the user's enabled add-ons or open scene. Logs and machine-readable results are written beneath ignored `build/test-runs/` folders.

The default suite contains 25 core/integration checks, 28 selection checks and 17 historical upgrade checks. Use `--suite core`, `--suite selection` or `--suite upgrade` for a focused run. Historical upgrade fixtures reproduce the cached-engine mismatch fixed in 1.1.1; they remain immutable. The core and selection suites test the current working source.

Build outputs go to ignored `dist/`: an installable extension ZIP, a delivery pack with both guides, and SHA-256 checksums. Versions are read from the manifest; the build fails if `bl_info` disagrees. The build does not install, publish or modify source.

## Source map

| Path | Purpose |
|---|---|
| `keyframe_reducer/core.py` | Numerical reduction and angular/vector distance |
| `keyframe_reducer/engine.py` | Action-slot processing and evaluated curve validation |
| `keyframe_reducer/selection.py` | Strict selection boundaries and outside preservation |
| `keyframe_reducer/__init__.py` | Blender properties, operators and panels |
| `tests/` | Blender integration and migration regressions |
| `tests/fixtures/releases/` | Original installation ZIPs for upgrade tests |
| `scripts/` | Portable packaging and isolated test runner |

Current validation concerns sampled local transforms, not continuous world-space error or foot-contact preservation. Reduction does not correct capture errors or remove jitter automatically. NLA results must be baked to an Action first. See the guides for the full limitations.

Private production scenes and third-party character assets are not included. Optional scene tests accept a locally supplied compatible fixture; see [tests/README.md](tests/README.md).

## Distribution

The add-on repository is the code/release authority. The portfolio website is a separate integration: reference the published add-on release and preserve its existing download counter pattern, like Select Similar. Development tasks in this repository must not silently deploy website changes.

No Maxon or Autodesk code is included. This project is not affiliated with Maxon, Autodesk or the Blender Foundation.
