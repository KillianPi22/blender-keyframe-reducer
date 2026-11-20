# Reference workflows and interactive preview acceptance criteria

Reviewed: 2026-11-20. Target: Blender 5.2.1, Graph Editor first. Addon UI stays in English; user guides remain available in English and French.

This document is a development specification. It does not claim feature parity, matching algorithms, or measured performance against Maya or Cinema 4D.

## Shipped baseline versus proposed work

Version **1.1.1** already reduces an Action on a protected copy, recalculates from its source, compares Original/Reduced, and keeps the result for editing. It supports whole-Action or selected-key scope, disjoint selection runs, optional selected bones, grouped transform reduction, local position/rotation/scale tolerances, and protected key types. These are existing behaviors to preserve and regression-test.

The next milestone is a **Graph Editor interactive preview session** with automatic parameter updates and explicit Apply/Cancel. Slider-driven automatic preview, the lifecycle below, and its performance targets are **planned**, not shipped in 1.1.1. World-space contact preservation and brush reduction are later candidates.

## Official product references

| Reference | Documented behavior | Design implication |
| --- | --- | --- |
| [Maya 2026: Key Reducer Filter options](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Animation/files/GUID-63E2EA0D-90E7-45EC-9AF3-D3097A8BA5B9.htm) | Preview; whole curve, selected portions, playback or explicit time range; absolute/percentage precision; synchronized sibling curves; tangent-type preservation. | Make scope and tolerance explicit. Keep separate selection islands. Borrow the preview workflow without assuming Autodesk's algorithm. |
| [Cinema 4D 2026: Key Reducer](https://help.maxon.net/c4d/2026/en-us/Content/html/Key_Reducer.html) | Interactive Strength, Magnet for nearby key alignment, and preservation of value/time-locked keys. It operates on complete F-curves, ignoring individual key selections. Maxon warns that it treats objects independently and does not account for skeletal dependencies. | Keep the primary controls simple. Our precise selection scope is an intentional extension. Magnet-style time shifts must not be silently introduced by channel synchronization. |
| [Blender 5.0: Editing F-Curves](https://docs.blender.org/manual/en/5.0/editors/graph_editor/fcurves/editing.html) | Native Decimate offers a removal ratio or an allowed curve-shape change. | Differentiate percentage of keys removed from error tolerance. The addon should add workflow and validation benefits beyond another decimation button. |
| [Maya 2026: Graph Editor toolbar](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Animation/files/GUID-A6061A36-81FF-4F57-A081-C967F749D546.htm) | A local key-reduction brush and buffer-curve comparison are available. | Prioritize A/B comparison now; consider a brush only after reliable scoped preview. |

The Blender reference describes established native behavior; compatibility with our actual 5.2.1 runtime must be tested locally. Maya's [filterCurve command](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Tech-Docs/Commands/filterCurve.html) also documents selection precedence and a quaternion flag; its brief flag description does not establish general quaternion guarantees for every filter.

## Next milestone: required acceptance checks

### 1. Nonaccumulating preview

- Starting Preview captures the source object, Action, slot, scope, selected bones/keys, and original assignment. Display this scope clearly.
- Every update starts from the same captured source, never the previous reduced preview. Settings A -> B -> A must produce the same keys and evaluated curves as a fresh run with A.
- Original/Reduced comparison does not alter the source, change the captured selection, or start a new reduction chain. Playback and scrubbing remain usable.
- Keep at most one displayed preview and one pending replacement per session. Repeated updates must not accumulate orphan Actions or fake users.

### 2. Apply and Cancel

- Apply commits only the latest completed result for the current parameters and source revision. Disable it while that result is unavailable; never silently apply an older preview.
- Apply retains a normal editable Action and the recoverable original. One undo returns to the pre-session assignment; redo restores the committed result. Test these operations in Blender, not just Python data mocks.
- Cancel restores the initial Action/slot assignment and source contents, including selection and handle metadata. It removes only session-owned temporary data with no external users.
- If the user manually assigned another Action or edited the preview, do not overwrite or delete that work on Cancel. End the session with a clear status and retain the edited data.

### 3. Selection and curve integrity

- Freeze the captured selection for the session; expose an explicit Restart/Refresh Selection action. Selecting preview keys must not silently redefine the source scope.
- Two selected islands separated by unselected keys remain separate. Preserve each island's boundary times and the entire unselected gap; never use one enclosing min/max range.
- Outside scope, preserve key times, values, handles, interpolation, easing and key types. Also compare evaluated values in adjacent spans, since automatic handles can affect neighboring segments.
- Hidden/locked channels stay excluded. Incomplete quaternion selection is preserved with an explanation; do not silently expand a selected scalar channel to unrelated channels.
- Verify normalized quaternion angular error for complete WXYZ groups, including equivalent opposite signs. Preserve intentional multi-turn Euler motion. Reduction does not implicitly perform smoothing or retiming.

### 4. Stale preview and failure handling

- Invalidate pending work when its source data, Action/slot, scope or ownership changes. Handle object deletion, undo/redo, file loading and addon unregistering without stale writes.
- Assign each request a generation ID. Publish a result only if its generation, source revision and owner still match; discard superseded work.
- If a session becomes stale, restore its source assignment only when the object still holds that session's owned preview. Respect any replacement assigned by the user.
- On calculation failure, retain the original and last valid preview, expose the error, and allow Cancel. Apply remains unavailable for invalid or outdated output.

### 5. Blender execution and responsiveness

- All `bpy` reads, writes, curve evaluation, Action assignment and redraw requests occur on Blender's main thread. Any background computation receives detached numeric data only and returns detached results.
- Coalesce rapid slider changes; use bounded main-thread work chunks where possible. Merely scheduling one long synchronous operation on a timer is not a responsiveness solution.
- Measure source snapshot, compute, validation, swap/redraw and total update times separately. Record source key count, channels, frame span, settings, Blender version and hardware.
- Benchmark small/medium/large fixtures around 10k/100k/500k keys, including a real mocap Action. Report median and p95 latency, cancellation latency, peak temporary Actions and maximum observed main-thread stall.
- Initial engineering targets, **not achieved claims**: visible pending feedback within 100 ms, at most 200 ms input coalescing, cancellation acknowledged within 200 ms, and p95 update within 500 ms on the 10k-key fixture. Report misses honestly and use a clearly labeled manual refresh mode where needed.

## Release gate

Keep the 1.1.1 regression suite passing. Add meaningful Blender integration checks for session lifecycle, source immutability, selection islands, repeated updates, stale work and undo/redo. Verify installation over 1.1.1 in a clean profile. Record numerical error and latency results; visually review an actual mocap take while scrubbing and playing. Local curve tolerance is not a promise of foot locking or unchanged end-effector trajectories.
