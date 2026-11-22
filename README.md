# Blender Keyframe Reducer

An independent, free Blender extension for reducing animation keys on a protected Action copy. Maintained by Killian Pichon. GPL-3.0-or-later.

[Repository](https://github.com/KillianPi22/blender-keyframe-reducer) | [Release 1.1.1](https://github.com/KillianPi22/blender-keyframe-reducer/releases/tag/v1.1.1) | [Installable ZIP](https://github.com/KillianPi22/blender-keyframe-reducer/releases/download/v1.1.1/keyframe_reducer-1.1.1.zip)

**Current baseline: 1.1.1. Requires Blender 5.2.0 or later; tested on Blender 5.2.1 LTS.**

**Working source: 1.5.0 development, not published.** Choose **Tool: Simplify Curve > Curve Style: Editable Bezier** to fit a smaller set of selected transform keys with aligned tangents for editing. **Keep Existing Handles** retains the 1.2 behavior and remains the default. Fitting explicitly rebuilds selected tangents, including manual handles, within unchanged local position, angular rotation and scale tolerances. Key Reducer remains available for grouped reconstruction. Editable Bezier now also offers an interactive preview; the other modes keep manual recalculation. All modes use protected source copies; **Restore Original** ends comparison and returns to the source. See [the fitting investigation](docs/EDITABLE_CURVES.md) for measured results and limitations.

This repository separates add-on development from the portfolio website and the Marionette Workflow Helper. The goal is an efficient animation cleanup workflow inspired by the usability of Maya and Cinema 4D. Feature parity is a development objective, not a claim about this release.

Version 1.4 introduced **Use Bone Animation Profile**, bounded anchor removal and
consolidation, dominant-extreme detection through small ripples, exact-hold seeds
and finer final validation with a retry. The profile keeps numeric tolerances.
The panel marks earlier results when settings or the bone filter change.

## Available now

- Reduce the active Action or selected, visible Graph Editor key runs.
- Preserve the original Action; compare Original / Reduced and recalculate from the source.
- Group XYZ transforms and complete WXYZ quaternions with sampled error checks.
- Protect significant extrema, marked keys and selected-run boundaries.
- Preserve unselected keys and handles, unrelated slots and unsupported channels.
- English interface; [English guide](keyframe_reducer/README_EN.md) and [French guide](keyframe_reducer/README_FR.md).

**Interactive preview is available for Simplify Curve / Editable Bezier in 1.5.0 development.** Choose **Start Interactive Preview**, adjust **Reduction**, compare Original / Preview, then Apply or Cancel. Processing is cooperative and automatic after a short pause; large scopes are not instantaneous. Other modes retain **Recalculate from Source**. See [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for scope and acceptance criteria.

[Official workflow references](docs/REFERENCE_WORKFLOWS.md) compare Maya, Cinema 4D and Blender behavior without promising feature equivalence.

## Install

Build the development extension ZIP, or use the published 1.1.1 release linked above. In Blender choose **Edit > Preferences > Add-ons > Install from Disk**, select the inner `keyframe_reducer-<version>.zip`, and enable the extension. In the Graph Editor press **N > Key Reducer**. Do not install the complete delivery pack.

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

The default suite includes core/integration, selection, simplify, fitting, interactive preview, historical upgrade and current-version installation checks. Use `--suite core`, `--suite selection`, `--suite simplify`, `--suite fitting`, `--suite preview`, `--suite upgrade` or `--suite upgrade_current` for a focused run. Historical upgrade fixtures reproduce the cached-engine mismatch fixed in 1.1.1; they remain immutable. The other suites test the current working source. Version 1.5.0 passes 253 checks in Blender 5.2.1 LTS; the installed extension's slider, comparison, Apply and Cancel were also checked in the Graph Editor.

Build outputs go to ignored `dist/`: an installable extension ZIP, a delivery pack with both guides, and SHA-256 checksums. Versions are read from the manifest; the build fails if `bl_info` disagrees. The build does not install, publish or modify source.

## Source map

| Path | Purpose |
|---|---|
| `keyframe_reducer/core.py` | Numerical reduction and angular/vector distance |
| `keyframe_reducer/engine.py` | Action-slot processing and evaluated curve validation |
| `keyframe_reducer/selection.py` | Strict selection boundaries and outside preservation |
| `keyframe_reducer/simplify.py` | Selected-run simplification, fitted handle writing and evaluated validation |
| `keyframe_reducer/fitting.py` | Blender-independent adaptive cubic fitting with shared slopes |
| `keyframe_reducer/preview.py` | Debounced cooperative preview, captured scope and temporary Action lifecycle |
| `keyframe_reducer/__init__.py` | Blender properties, operators and panels |
| `tests/` | Blender integration and migration regressions |
| `tests/fixtures/releases/` | Original installation ZIPs for upgrade tests |
| `scripts/` | Portable packaging and isolated test runner |

Current validation concerns sampled local transforms, not continuous world-space error or foot-contact preservation. Reduction does not correct capture errors or remove jitter automatically. NLA results must be baked to an Action first. See the guides for the full limitations.

Private production scenes and third-party character assets are not included. The unchanged historical guides describe a scene supplied with the original private delivery; that scene is absent from this public repository and its new delivery pack. Optional scene tests accept a locally supplied compatible fixture; see [tests/README.md](tests/README.md).

GitHub's build workflow checks Python syntax and package integrity. It does not run Blender. The release workflow publishes only when `release.json` is explicitly changed on `main`, a matching version tag is pushed, or it is manually triggered; existing release assets are never overwritten. Each requested version needs matching source metadata and a release note under `docs/releases/`.

## Distribution

The add-on repository is the code/release authority. The portfolio website is a separate integration: reference the published add-on release and preserve its existing download counter pattern, like Select Similar. Development tasks in this repository must not silently deploy website changes.

No Maxon or Autodesk code is included. This project is not affiliated with Maxon, Autodesk or the Blender Foundation.
