# Keyframe Reducer development brief

## Purpose and confirmed choices

Give Blender animators a practical, controllable key-reduction workflow, with the convenience expected from Maya or Cinema 4D. The add-on should help turn dense mocap into editable animation while preserving the user's intent and a recoverable source.

Confirmed by Killian Pichon on 2026-11-20:

- Develop in a dedicated GitHub repository through Codex.
- First priority: interactive preview while adjusting settings.
- Primary interface: Graph Editor.
- Keep the interface in English, with English and French guides.
- Reference the add-on from the portfolio site and keep download tracking consistent with the Select Similar download workflow.

The released baseline is 1.1.1. Current source is an unpublished 1.5.0 development build with interactive preview for Simplify Curve / Editable Bezier. Key Reducer and Keep Existing Handles retain manual calculation.

Confirmed on 2026-11-21: add a distinct **Simplify Curve** tool inspired by Unreal's tolerance-based workflow, preserving the curve's shape rather than smoothing oscillations. The development implementation works on selected transform keys, keeps source interpolation, protects manual tangent keys by default, and exposes tolerances directly. Position/scale/Euler axes are independent; complete WXYZ curves remain grouped and angularly validated. It shares source-copy comparison and manual recalculation with Key Reducer. General scalar-property coverage remains future work; see the 1.5 preview follow-up below.

Follow-up on 2026-11-21: the animator needs a small set of bone-curve controls with meaningful tangents, not only removal of redundant points. **Curve Style: Editable Bezier** fits shared interior slopes and adaptively adds source key times where the measured error requires them. It explicitly rebuilds selected tangents, including manually set ones. **Keep Existing Handles** retains 1.2 behavior and remains the default for compatibility. Numerical tolerances are unchanged. The selected-bone filter uses Blender 5.2 pose-bone selection, and result counts describe the filtered scope. A generated 241-key bone rotation needs 9 keys with fitting versus 54 with the older method at the same 0.5-degree limit; production-character fidelity has not been established from screenshots.

The 1.4.0 follow-up adds bounded removal/consolidation of fitted anchors, dominant
extrema through small ripples, exact-hold seeds and finer final validation. The
Bone Animation profile prepares the intended workflow without loosening numeric
limits. Settings changes visibly require recalculation. The user authorized
further development without the production scene after its transfer failed.

## Baseline

1.1.1 reduces transform channels in the active Action slot, on a protected copy. It supports entire-Action and selected-key scopes, disjoint selected runs, grouped XYZ/WXYZ, local position/rotation/scale tolerances, marked-key protection, Bezier or linear output and manual before/after comparison. Recalculation explicitly starts from the source. Upgrade tests reproduce and prevent the stale-module `key_selection` error.

Current error bounds are sampled local-transform checks. Character extremities can move further in world space because bone errors accumulate. This release does not perform contact locking, capture correction, smoothing, NLA-stack reduction, general scalar-channel reduction or automatic preview for Key Reducer / Keep Existing Handles.

## Milestone 1: interactive Graph Editor preview

The 1.5.0 prototype implements the Editable Bezier workflow below, with cooperative
numerical/sampling/write steps, a 180 ms debounce and temporary Action cleanup.
The Reduction slider multiplies the explicit base tolerances; it is not a forced
key budget. Scope stays captured. Pending work cannot be applied. Saving closes
an unapplied preview and restores the starting assignment; Apply before saving.
Performance targets below remain goals, not achieved guarantees. See
[preview details and measurements](docs/INTERACTIVE_PREVIEW.md).

User feedback after trying 1.5: adjusting the rotation control from 1 to 2 gives
better results on the user's case. Keep the current defaults; this is qualitative
feedback rather than a measured general-purpose tolerance recommendation. The
user authorized updating the GitHub repository with the current implementation.

Workflow: select channels or key runs, start **Preview**, adjust strength/tolerances, compare source and result, then **Apply** or **Cancel**. Keep the common controls visible and move specialist options behind a compact advanced section.

Acceptance criteria:

1. Parameter changes request a debounced recalculation from the captured source. Dragging a slider must not queue every intermediate value.
2. The UI remains responsive on representative mocap Actions. Expensive work is cancellable and stale preview requests cannot overwrite newer results.
3. Apply keeps an editable reduced Action. Cancel restores the starting Action/slot and selection without modifying the source or leaving orphaned previews.
4. Original/Reduced comparison and key-count statistics update clearly. A pending or failed preview cannot be mistaken for the final result.
5. Empty selections, disjoint windows, selected bones, complete quaternions, NLA Tweak Mode and unsupported channels retain safe current behavior.
6. Selection changes are explicit: the captured selection remains stable until the user chooses a new selection.
7. Undo/redo, switching active objects/Actions, save/reopen, add-on reload and cancellation are covered by regressions before release.
8. Blender data access stays on Blender's main thread. Source sampling/caching and chunked scheduling must be designed before claiming real-time performance.

Performance targets should be measured on the existing dense mocap benchmark and a generated large Action. Record time to first preview, recalculation time, key count and measured error before choosing a numerical latency promise.

## Following milestones

| Milestone | Candidate work | Quality gate |
|---|---|---|
| Scope and feedback | Frame range, clearer units, Graph Editor overlays, visible protected keys and preservation reasons | No changes outside the requested scope; understandable error display |
| Curve editing coverage | Explicit scalar channels such as custom properties, shape keys and lens curves; configurable channel grouping | Property-appropriate tolerances and unsupported-type handling |
| Reduction controls | Optional target key count/ratio, saved presets, synchronized pose times and bounded key-time adjustment | Report when a target conflicts with fidelity; retain deterministic source comparison |
| Character fidelity | Optional world-space checkpoints and hand/foot contact-aware validation | Evaluate hierarchy/constraints and measure drift against the source |
| Production scale | Batch Actions, guided NLA bake, large-clip profiling and release automation | Isolated copies, progress/cancel, reproducible tests and explicit output ownership |

These are proposals for later prioritization, not promised features. A target key count must never silently override a fidelity limit. Contact-aware reduction is different from repairing an already distorted mocap take.

## Repository and release boundaries

- The add-on repository contains source, guides, tests and reproducible packaging.
- Immutable historical installer ZIPs are test fixtures, not the main source tree.
- Production character scenes remain private and outside the public repository.
- Build artifacts are generated locally; publication and website deployment are separate actions.
- The website should link the intended released asset through its existing download-count mechanism. Avoid counting repository visits or documentation clicks as downloads.

## Open design decisions after the first prototype

- Whether the 3D View convenience panel should mirror the Graph Editor preview or only provide comparison/apply controls.
- Whether an error tolerance, target reduction ratio or named quality preset should be the primary artist control.
- Which scalar channels and world-space contact scenarios provide the most value after preview is reliable.

These questions need not block the preview prototype.
