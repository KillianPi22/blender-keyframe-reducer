# Keyframe Reducer development brief

## Purpose and confirmed choices

Give Blender animators a practical, controllable key-reduction workflow, with the convenience expected from Maya or Cinema 4D. The add-on should help turn dense mocap into editable animation while preserving the user's intent and a recoverable source.

Confirmed by Killian Pichon on 2026-11-20:

- Develop in a dedicated GitHub repository through Codex.
- First priority: interactive preview while adjusting settings.
- Primary interface: Graph Editor.
- Keep the interface in English, with English and French guides.
- Reference the add-on from the portfolio site and keep download tracking consistent with the Select Similar download workflow.

The source in this initial repository is unchanged version 1.1.1. Creating the repository does not implement preview or create a new add-on release.

## Baseline

1.1.1 reduces transform channels in the active Action slot, on a protected copy. It supports entire-Action and selected-key scopes, disjoint selected runs, grouped XYZ/WXYZ, local position/rotation/scale tolerances, marked-key protection, Bezier or linear output and manual before/after comparison. Recalculation explicitly starts from the source. Upgrade tests reproduce and prevent the stale-module `key_selection` error.

Current error bounds are sampled local-transform checks. Character extremities can move further in world space because bone errors accumulate. This release does not perform contact locking, capture correction, smoothing, NLA-stack reduction, general scalar-channel reduction or automatic live preview.

## Milestone 1: interactive Graph Editor preview

Proposed workflow: select channels or key runs, start **Preview**, adjust strength/tolerances, compare source and result, then **Apply** or **Cancel**. Keep the common controls visible and move specialist options behind a compact advanced section.

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
