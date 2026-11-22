# Interactive Editable Bezier preview — 1.5.0 development

The animator can now explore point density without pressing Recalculate after
each tolerance change. In the Graph Editor choose Simplify Curve / Editable
Bezier (or the Bone Animation profile), select keys, then Start Interactive
Preview. Reduction scales the base tolerances. At rotation 0.5°, values 0.5 / 1 / 2
allow 0.25° / 0.5° / 1°. Counts are measured from the completed result, not predicted
percentages. The heuristic does not guarantee monotonically fewer keys for every
input, and significant motion cannot disappear while preserving a tighter limit.

## Session behavior

- Capture visible selected runs and the bone filter once. Existing manual
  comparisons reuse their immutable source and captured range; cancellation
  restores the starting manual comparison too.
- Make an independent source snapshot. Every slider request uses it, never the
  previously reduced curves. Keep the last completed result visible during work.
- Coalesce parameter changes after 180 ms. Superseded generators and private work
  Actions are discarded. Only the latest completed generation is published.
- Compare Original / Preview during calculation. Original remains displayed if
  the user chooses it while a result is being calculated.
- Disable Apply while waiting, computing or failed. Apply makes an ordinary
  editable Action and ends automatic updates; one undo restores the starting
  assignment and redo restores the committed result.
- Keep comparison, Apply and Cancel above the changing progress/result text so
  their positions do not jump as calculations finish.
- Cancel restores the starting Action, slot and selections and removes unused
  temporary IDs. If a preview has been edited or linked elsewhere, retain it as
  user data instead of deleting it. Source/slot/object/Action changes invalidate
  obsolete work. Animation fingerprints exclude selection changes.
- History, file loading and add-on reload close runtime state. Save cancels an
  unapplied session before serializing the file. Apply before saving. Temporary
  IDs restored by undo are recovered to their original assignment and cleaned.

The current preview is only for Editable Bezier. The Key Reducer and Keep
Existing Handles paths continue to use manual calculation. No smoothing,
world-space/contact constraint or continuous-error guarantee is added.

## Execution and performance

All Blender access stays on the main thread. Numerical fitting, source sampling,
curve writing and validation expose cooperative steps. The timer processes about
12 ms of work per callback, then returns control. A single Blender operation
such as copying an Action cannot be preempted by this budget. Progress redraws
target sidebar regions and do not force full viewport rendering every tick.

Source and displayed-result fingerprints use native bulk reads of curve data,
including handles, interpolation, modifiers, sampled curves and other slots.
They catch external edits before publication/application. This validation and
retaining complete Action copies have a cost even when only one bone is fitted.

Generated benchmark: 600 Euler channels × 1,241 keys = 744,600 keys; one captured
bone contributes 3,723 keys. Directly pumping the same timer callback (without
Blender's scheduling delays) measured:

| Reduction | Result keys | Compute time | Callbacks | Longest callback | 95th percentile |
|---|---:|---:|---:|---:|---:|
| 1 | 99 | 2.81 s | 206 | 177 ms | 12.4 ms |
| 2 | 86 | 2.29 s | 176 | 159 ms | 12.5 ms |
| 1 again | 99 | 2.60 s | 212 | 23 ms | 12.5 ms |

Initial capture/copy took 0.48 s and cancellation/checking/cleanup 0.76 s. These
are single-run synthetic measurements, not end-to-end UI latency promises;
actual timer scheduling adds time. The 500 ms preview and 200 ms cancellation
targets in the planning document are not achieved on this large Action. Smaller
Actions and shorter selections are preferable. Further caching and copying
improvements remain useful; the current gain is automatic updating with responsive
work intervals, not constant-time whole-rig reduction.

## Validation

The preview suite exercises real Blender data and operators, driving the actual
timer callback without sleeps. It covers coalescing, A/B/A determinism, frozen
scope, exact gaps/other slots, full quaternions, unsupported modifiers, source
and displayed edits, shared results, pending/error Apply guards, cancellation,
undo/redo, save/reopen and reload cleanup. Existing numerical and selection
suites run the same cooperative engine synchronously and retain their checks.

All seven suites pass 253 checks in Blender 5.2.1 LTS. Native Graph Editor checks
with the installed ZIP cover slider dragging, automatic count/curve updates,
Original / Preview, Cancel, Apply and reinstalling during an active session.
A generated 331-key selection produces 13 keys at Reduction 1 and 11 at 2.

The production Minotaur scene was not used. This development iteration follows
the user's instruction to continue without it.
