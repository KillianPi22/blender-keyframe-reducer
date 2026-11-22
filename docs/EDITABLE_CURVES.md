# Editable bone-curve investigation — 2026-11-21

The animator's reference calls for a few useful curve controls whose values and
tangents describe the motion. The 1.2 implementation could retain many keys even
on a smooth arc. Raising the tolerance alone does not address that limitation.

## Diagnosis

- The legacy Simplify path seeds keys using a piecewise-linear approximation,
  then only adds keys while validating the actual result. A cubic arc that needs
  two well-fitted handles may therefore inherit many unnecessary linear anchors.
- Manual handle protection can retain most or all of a bake exported with Free
  or Aligned handles. It is useful for authored curves but is not a general test
  of which mocap samples are meaningful animation controls.
- The submitted screenshot shows 739,725 captured keys and Selected Bones Only
  disabled. It does not establish a per-bone quality result or show the final
  key count. It is insufficient to measure foot contact, hierarchy error, Euler
  discontinuities or the rig's unit scale.
- A real generated-armature test exposed a separate Blender 5.2 bug: selection
  must be read from `PoseBone.select`, not `Bone.select`. The new code fixes both
  processing and the displayed bone-filter count.

## Implemented in 1.3.0 development

**Simplify Curve > Curve Style: Editable Bezier** begins with the selected run's
endpoints and protected extrema/marked times. It fits cubic segments jointly,
using a common tangent direction at interior keys. Flat extrema/plateaus are
constrained during the fit, and slope limits prevent new extrema between anchors.
It adds source key times at failing spans, checks local error, writes aligned
interior Bezier handles, then checks Blender's evaluated result. An unsupported
or failed fit retains the source keys. The retained values and times are unchanged.

This option deliberately replaces selected tangents, including manual ones.
It converts selected linear segments to Bezier. Boundary outward handles,
outside interpolation, disjoint gaps and unrelated channels/slots stay intact.
The source Action is copied and recalculation reuses it. Quaternion components
remain grouped and their errors use normalized orientation; Euler values are
never wrapped modulo a revolution.

**Keep Existing Handles** remains the default for existing workflows. It retains
the old manual-handle protection option. Position/rotation/scale defaults were
not loosened: a rig's scale and contact requirements must determine them.
The panel now reports keys within the processed scope rather than counts that
include bones excluded by the filter. Per-curve counts, tolerances and measured
errors are recorded in the generated Action's `kr_report` property.

## Reproducible shape check

Run the `fitting` suite through `scripts/run_tests.py` in Blender 5.2.1 LTS.
The generated Upper-bone Euler curve is a dense 241-key series with peaks,
troughs and a shoulder; a second animated bone is parented to it. The table is
for the Upper rotation curve only. Manual-handle protection is disabled in the
legacy comparison so that it does not artificially favor the new method.

| Method | Source keys | Result keys | Allowed error | Measured maximum |
|---|---:|---:|---:|---:|
| 1.2 Keep Existing Handles | 241 | 54 | 0.5° | 0.1312° |
| 1.3 Editable Bezier | 241 | 12 | 0.5° | 0.2660° |

Both results are checked independently at eighth-frame intervals. The new
method uses more of the same error allowance; it does not promise the old
method's smaller observed error. A separate 121-key baked ease reduces to two
controls. These fixtures show the effect of fitted tangents, not a guarantee of
minimum key count or animator-approved poses on arbitrary mocap.

A separate generated Action contains 600 Euler curves over 1,241 frames
(744,600 keys). On the development machine, fitting one named bone's three axes
processed 3,723 keys into 133 in 0.63 seconds, including the Action copy. Fitting
all curves produced 27,022 keys in 45.43 seconds. Reported sampled error stayed
below 0.5°; independent eighth-frame checks covered all three axes for the single
bone and 20 evenly spaced channels in the full run. These are one-run timings
on synthetic data, not a latency guarantee. The current synchronous operation
can stall Blender during a full-rig calculation.

## Practical trial on the user's rig

1. Work from the protected source and select one or two bones in Pose Mode.
2. Select a representative key range in the Graph Editor.
3. Choose Simplify Curve, Editable Bezier and Selected Bones Only.
4. Start with rotation tolerance 0.5° and keep significant extrema and marked
   keys protected. Keep position tolerances conservative until rig units are known.
5. Recalculate, compare Original / Simplified while scrubbing and playing, and
   inspect the bone's curve handles. Check planted feet and hands in the viewport.
6. Keep Copy for Editing before moving keys or tangents manually.

Automatic live preview and world-space/contact constraints are not implemented.
Fitting is synchronous and may take time on large scopes. No production Minotaur
Action has been analyzed: that requires a copy containing the armature, relevant
constraints and animation; the mesh is optional.

## Implemented in 1.4.0 development

The follow-up targets redundant clusters after tangent fitting. The engine now:

- Seeds exact hold boundaries as removable anchors.
- Tracks dominant extrema through reversals smaller than twice the tolerance,
  rather than protecting the first small ripple after a long arc. This changes
  anchor selection only; the source samples are never filtered.
- Removes unnecessary unprotected controls with local tangent refits, then
  consolidates adjacent unprotected pairs at better source key times. Candidate
  times include representative interval positions and low-velocity shoulders.
- Holds derivatives at the edges of each refit window, so other segments remain
  unchanged. Three removal sweeps and two consolidation sweeps use bounded sample
  budgets. The result is deterministic, not a globally minimal key solution.
- Checks Blender at eighth points between original keys. If that finer check
  fails, retries fitting with those source samples before restoring on failure.

The new **Use Bone Animation Profile** button prepares FIT, selected bones,
significant extrema and marked-pose protection without changing numerical
limits or calculating automatically. **Settings changed: Recalculate** identifies
results from previous settings or bone filters. Existing settings and operators
remain compatible; Keep Existing Handles remains the fallback default.

Generated comparisons at the same 0.5-degree tolerance:

| Curve | 1.3 keys | 1.4 keys | Maximum eighth-frame error in 1.4 |
|---|---:|---:|---:|
| Shoulder | 12 | 9 | 0.0083° |
| Fast transitions | 15 | 10 | 0.4651° |
| Long holds | 11 | 6 | below 0.0001° |
| Arc with small ripples | 12 | 4 | 0.4727° |
| Mixed arcs over 1,241 frames | 46 | 35 | 0.4820° |
| Time-weighted source ease | 3 | 3 | 0.2475° |
| Brief gesture between holds | 5 | 5 | 0.4584° |
| Larger oscillations | 204 | 204 | 0.4696° |

The generated regression suite independently checks the new results at sixteenth
frames, including eight additional mixed-frequency curves at 0.25°, 0.5° or 1°
and changing-axis quaternion motion. A narrow error peak on the larger-oscillation
case at 1° exposed the old quarter-grid limit; the finer retry corrects it. This
still establishes sampled local accuracy only, not a continuous guarantee.

The small-ripple example needs 23 keys at 0.25° but only four at 0.5°: fitting
cannot both remove every oscillation and preserve a tighter shape budget. The
larger-oscillation example deliberately retains many controls. No smoothing
filter or forced key-count target has been introduced. More tolerance does not
promise monotonically fewer keys from this bounded heuristic on every input.

Reproduce with `scripts/benchmark_editable.py`, using the locally delivered
1.3.0 ZIP as baseline. `scripts/plot_editable_study.py` optionally plots its JSON
using matplotlib; the add-on itself remains dependency-free. Tests use generated
curves, not the uploaded character scene. After its transfer failed, the user
explicitly requested continued development without that scene. No Minotaur
result or equivalence to Unreal is claimed.

The larger generated benchmark improves from 27,022 to 20,697 resulting keys
out of 744,600. One bone's 3,723 keys become 99 in 1.64 seconds; the full Action
takes 221.73 seconds. This additional search costs considerably more than 1.3
(0.63 / 45.43 seconds respectively in the earlier run). Reported sampled error
stays below 0.5° and independent eighth-frame checks cover the three selected
axes or 20 spread-out channels in the full run. These are single-run synthetic
measurements, not latency guarantees. Selected-bone work is recommended while
the operation remains synchronous.
