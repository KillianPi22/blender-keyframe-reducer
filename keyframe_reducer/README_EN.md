# Keyframe Reducer 1.5.0 — development build

The published stable release remains 1.1.1. This guide describes the unpublished
1.5.0 source, including **interactive preview for Editable Bezier**.

Free Blender 5.2 add-on, developed and tested in **Blender 5.2.1 LTS**.
Inspired by working with Cinema 4D's Key Reducer. It does not reproduce its
algorithm or its Magnet feature.

The plugin interface is in **English**, including buttons, options, tooltips and
messages. [Guide français](README_FR.md).

## Installation

1. Extract the delivery **pack**.
2. In Blender, open **Edit > Preferences > Add-ons > top-right menu > Install from Disk**.
3. Select **keyframe_reducer-1.5.0.zip**. Do not extract this inner ZIP.
4. Enable **Keyframe Reducer** if necessary.
5. In the 3D View or Graph Editor, press **N** and open **Key Reducer**.

Requires Blender 5.2.0 or later. No dependencies, network access, account or special
permissions are required.

To update an older version, install the new ZIP in the same location and allow
replacement. Save your project and restart Blender if the old interface remains.

## Editable Bezier: fewer bone controls with fitted tangents

For animation editing, choose **Tool: Simplify Curve > Curve Style: Editable
Bezier**. This fits Bezier tangents as well as removing keys. It can represent a
smooth arc with a few useful controls instead of many samples along the arc.

1. Select one or two bones in Pose Mode, then select a representative range of
   their key points in the Graph Editor.
2. Click **Use Bone Animation Profile**. This chooses **Simplify Curve > Editable
   Bezier**, enables **Selected Bones Only** and protects significant extremes and
   marked poses. It keeps your numeric tolerances and does not start a calculation.
3. Start with **Rotation: 0.5°**. The position and scale limits remain unchanged;
   position is in local rig units. A lower limit keeps more of the source detail.
4. Click **Start Interactive Preview**, then drag **Reduction**. The key counter
   and curves update automatically after a short pause. Compare **Original / Preview**.
5. Choose **Apply Preview** to edit the result, or **Cancel** to restore the start.

### Interactive controls

Reduction multiplies the base error tolerances: at rotation 0.5°, Reduction 0.5
allows 0.25°, while Reduction 2 allows 1°. Higher values generally permit fewer
keys. This is an error allowance, not a target key count or percentage.
Effective limits are visible beside the slider; base limits remain under the
options. Changes restart from a frozen source copy and replace pending requests.

The last completed result stays visible while a new one is calculated. Its count
is marked as the previous result; **Apply Preview** becomes available only when
the current request has finished. Scope is captured once, including selected
bones and separate key runs. Changing the visible selection does not expand it.
When continuing a manual comparison, preview reuses its original captured range.
To choose a different range, end that comparison with Restore Original or Keep
Copy for Editing, select the new range and start another preview.

Cancel restores the starting Action, slot and selection and removes unused
temporary Actions. Apply keeps an ordinary editable Action and stops automatic
updates. Undo/redo, loading, disabling/updating the extension and saving close
an active preview. **Apply before saving**; otherwise the unapplied preview is
cancelled and the starting Action is saved. If a displayed preview was edited
manually, it is retained rather than deleted; apply before editing for the normal
workflow. A source edit or different active object/Action stops obsolete work.

Numerical work, sampling and curve writes run in small main-thread steps. Large
Actions still take time, and copying, checking or disposing of Blender data can
cause short pauses. This is automatic, cancellable updating, not an instant
full-rig guarantee. Start with one or two bones and a short range.

**Simplify Selected Keys / Recalculate from Source** remain available for one-off
manual calculations; use **Keep Copy for Editing** after those operations.

The panel shows **Settings changed: Recalculate** while the visible result belongs
to earlier settings or a different bone filter. Recalculation remains manual.

Editable Bezier **rebuilds selected tangents, including manual handles**, and
converts selected linear segments to Bezier. Interior handles are Aligned, with
a shared slope on either side of a key. Significant extrema and marked key times
can remain protected; retained key values and times are unchanged. The outward
handles at selection boundaries and the unselected motion remain intact.

The result counter now shows the keys actually in scope after bone filtering.
Per-curve counts and sampled errors are stored in the result Action's `kr_report`.
The fitter removes redundant anchors after solving tangents and can replace two
unprotected keys with one better placed source key. Exact hold boundaries guide
the initial fit. Significant-extreme detection tracks the dominant peak through
small ripples; all candidates are still checked against the original curve.

At the same 0.5° limit, generated curves compare as follows:

| Shape | Editable Bezier 1.3 | Editable Bezier 1.4 |
|---|---:|---:|
| 241-key curve with a shoulder | 12 | 9 |
| 241-key fast transitions | 15 | 10 |
| 361-key movement with long holds | 11 | 6 |
| 361-key arc with small ripples | 12 | 4 |

These are synthetic examples, independently checked at sixteenth frames. They
do not establish fidelity on the Minotaur rig or guarantee a minimum key count.
Final Blender validation checks eighth points between source keys; a failed
candidate retries with the finer samples, then preserves the source if needed.

Use 0.25° for more detail, 0.5° as a starting point, or 1° when larger deviations
are acceptable. These are angular error limits, not quality guarantees or key
budgets. Position depends on local rig units. Oscillations exceeding the chosen
limit must remain represented; removing them would require more permitted shape
change or a separate smoothing operation. No smoothing filter is applied here.

**Keep Existing Handles** remains the default for compatibility with version 1.2;
select Editable Bezier or the Bone Animation profile for interactive work. No
smoothing, Euler filtering or world-space contact locking is added. The manual
Recalculate operation still runs synchronously; interactive preview uses the
same fitting result with cooperative processing. Keep Existing Handles and Key
Reducer continue to use the manual workflow.

## Simplify Curve: keep existing handles (1.2 behavior)

1. Select transform key points in the **Graph Editor**. Use **A** to select all
   visible keys, or box-select one or several sections.
2. In **N > Key Reducer**, choose **Tool: Simplify Curve > Curve Style: Keep Existing Handles**.
3. Set **Allowed Shape Change**: Position / Axis uses local rig units, Rotation
   uses angular units, and Scale / Axis uses scale factors. Smaller tolerances
   retain more detail. These values are error limits, not percentages of keys removed.
4. Leave **Protect Manual Tangents** enabled to retain Bezier keys whose handles
   are Free or Aligned. Disable it only to allow removing those keys as well.
5. Click **Simplify Selected Keys**, then compare **Original / Simplified**.
   Change a tolerance and click **Recalculate from Source** to try another result.
6. Choose **Keep Copy for Editing** to continue manual editing, or **Restore
   Original** to return to the source and close comparison. Restore keeps the
   generated result in the Action list for recovery.

**Keep Existing Handles** removes redundant keys while preserving surviving values,
times and interpolation. Automatic interior tangents may be recalculated;
surviving manual handles are retained. Boundary handles keep their positions
and become Free to protect the adjoining unselected spans. **Key Reducer** uses
its existing grouped reconstruction and Bezier/Linear output settings instead.

Simplify always uses selected keys, including when Key Reducer's Scope is Entire
Action. Position, scale and unwrapped Euler axes simplify independently, even
with different selection windows. Quaternion WXYZ keys must be selected together;
their error is measured as an orientation. Strength and output interpolation
settings from Key Reducer do not affect Simplify.

Three consecutive selected keys are required per run. Gaps, isolated keys,
unselected curves, other slots and the source remain intact. Only transform
curves are supported in this version; custom properties and shape keys are not.
Modified, locked, muted, sampled or unsupported interpolation is preserved.
Marked-key and significant-extrema protection is available under the options.

The comparison freezes the captured key selection. **Simplify New Selection**
explicitly captures the displayed Action as a new source; use it to work on
another section after comparing. Switching tools or scope otherwise keeps the
protected source. Recalculation is manual and replaces edits to the result, so
finish comparison before editing keys. Checks sample local curves, including
between source keys; they do not guarantee continuous or world-space fidelity.
This tool does not smooth jitter or retime animation.

## Fix in 1.1.1: consistent modules after an update

Version 1.1.0 could show `Settings.__init__() got an unexpected keyword argument
'key_selection'` when installed over version 1.0.0 in the same Blender session.
The interface was updated, but the old Python engine remained in memory.
Version **1.1.1 refreshes the components in dependency order** during an update.
The panel title now displays its version.

If you are still using version 1.1.0, saving your scene and fully closing and
reopening Blender also clears the old engine. This issue is unrelated to which
keys you select.

## New: reduce selected keys only

1. In the **Graph Editor**, display the channels you want to edit and select the
   **key points**, for example using **B** for Box Select.
2. Open **N > Key Reducer** and choose **Scope: Selected Keys**.
3. Adjust **Strength**, then click **Reduce on a Copy**.
4. Compare **Original / Reduced**. **Recalculate from Source** reuses the captured
   selection even if your visible selection has changed in the meantime.
5. To process another section, display **Reduced**, select its keys and click
   **Reduce New Selection**. This uses the displayed Action as the new source,
   preserving the reductions already visible in that Action.
6. Click **Keep Copy for Editing** before making manual corrections.

Each run of at least **three consecutive selected keys** is processed separately.
An unselected key breaks the run: you can select several sections without reducing
the motion between them. The first and last keys of every run are retained.
Isolated keys and selections containing only two keys are left unchanged.

- Unselected keys keep their values, handles, types and selection flags. The
  inward handles of selected boundary keys may change; their outward handles are
  preserved to retain motion outside the selected section.
- Channels hidden or filtered out of the Graph Editor, and locked channels, are
  excluded when capturing the selection. Select key points, not just handles.
- For location, scale and Euler rotation, only axes with selected keys participate.
  If several axes participate, their runs need selected keys at matching times.
  A missing or unselected key breaks the common run.
- For **quaternion rotation**, select **W, X, Y and Z together** at the same times.
  Partial quaternion selections are preserved and reported in the panel.
- An empty selection displays an error; it never triggers a whole-Action reduction.
  Custom properties are still excluded from reduction.
- Capture the initial or a new selection from the Graph Editor in **F-Curves** mode.
  Once captured, it can also be recalculated from the 3D View. The Dope Sheet is not
  used to capture the selection.

The captured selection and comparison are saved in the .blend file. Changing
Scope retains the protected source; **Reduce New Selection** explicitly rebases
on the displayed Action.

## General workflow

1. Select the armature and its **active Action**, with the correct slot.
2. For a complete NLA sequence, first use **Strip > Bake Action** in the NLA Editor
   with Visual Keying enabled, Pose, and no overwrite of the current Action. Then
   disable the original NLA tracks. The add-on reduces an Action, not the NLA stack.
3. Choose **Scope: Entire Action**, adjust **Strength**, then **Reduce on a Copy**.
4. Play the animation and switch between **Original / Reduced** to compare.
5. Adjust Strength or the tolerances and click **Recalculate from Source**.
   Recalculation starts from the source without accumulating reductions.
6. Click **Keep Copy for Editing**, then fix keys in the Graph Editor.

The original and reduced Actions are retained when saving the .blend file. The
add-on does not save files for you; save your project normally. Comparison remains
available after saving and reopening when the add-on is enabled.
Manual edits made to the preview before **Keep Copy for Editing** will be replaced
by the next recalculation. Finish comparison before editing keys.

## Settings

| Option | Effect |
|---|---|
| Strength | Multiplies tolerances. 0.5 retains more detail; 1 is the default; 2 allows twice the error. |
| Smooth Bezier | Rebuilds Auto Clamped handles, preserves endpoint velocity and validates Blender's actual evaluated curves. |
| Linear | Uses linear interpolation, useful for mocap imports and sometimes more efficient. |
| Position | Maximum vector error in **local units**, before armature scale. The test rig has scale 0.01, so 0.1 local unit corresponds to about 0.001 world unit for a direct translation. |
| Rotation | Quaternion angular error; vector error of unwrapped Euler angles to retain complete turns. Default: 0.5 degrees. |
| Scale | Vector error of scale factors. Default: 0.001. |
| Selected Bones Only | Processes selected bones in Pose Mode. Other bones and object transforms remain unchanged. |
| Keep Significant Extremes | Protects meaningful direction changes in location, scale and Euler channels. Quaternion orientation is protected by angular tolerance. |
| Protect Extreme / Breakdown Keys | Retains times marked with these key types. Useful for protecting a specific pose. |
| Validate Every 0.25 Frame | Finer sampling; the default checks every 0.5 frame. Original key times are always checked too. |

In **Entire Action** mode, keys are aligned **per property**: XYZ location, XYZ
scale, XYZ Euler or WXYZ quaternion. The add-on does not force all bones or
properties to share the same pose times, and does not shift keys like C4D Magnet.

## Protection and limitations

- The source is copied. Other slots in the Action remain unchanged.
- Custom properties, including Mixamo's `lockInfluenceWeights`, are preserved.
- Locked, muted or modified channels preserve their transform group. Constant or
  special interpolation also prevents reduction of the affected group or run.
- Incomplete quaternions and quaternion sign discontinuities are preserved.
- In Entire Action mode, groups with different channel start/end times are
  preserved. Selected Keys mode only processes common selected runs.
- If reconstruction cannot meet the tolerance, the original group or run is restored.
- Group boundaries and protected marked keys are retained. Output uses existing
  key times; no additional fractional key times are introduced.
- **Validation uses samples of local transforms**. It is not a continuous guarantee
  at every instant or a world-space foot contact constraint. Small rotation errors
  can accumulate along a bone chain. IK or contact key corrections may still be needed.
- Reduction does not automatically remove mocap jitter or capture errors.
- Only the active Action is processed. Exit NLA Tweak Mode before use.

## Included test scene

`TestImportMixamoAnim1_KeyReducer.blend` is a **copy** of the supplied scene.
The visible motion from frames 1 to 250 was baked into `KR_Montage_Source`, then
reduced. NLA tracks are retained, but NLA evaluation is disabled on the armature
to prevent adding the original sequence over its bake. The reduced Action is
active. Use **Original / Reduced** to compare the two Actions.

With Strength 1, rotation tolerance 0.5 degrees, Bezier and 0.25-frame validation:

| Test | Before | After | Reduction |
|---|---:|---:|---:|
| Isolated Swing | 38,480 | 14,840 | 61.4% |
| Isolated DropKick | 45,760 | 17,854 | 61.0% |
| Baked sequence 1-250 | 164,750 | 89,062 | 45.9% |

The previously edited `Action` is reduced more conservatively: 6,781 to 6,037 keys.
Its channels often have different endpoints, so those groups are preserved.

The bake reproduces the original sequence to approximately 0.0000035 world unit
at the bone positions sampled every frame. After reduction, the maximum measured
error is about **0.0138 world unit**, including 0.0127 at hand/foot extremities.
At this scene's metric scale, this is about **1.4 cm**. Lower rotation tolerance
for precise contacts. These measurements describe this scene and these settings,
not all animations.

The 25 original automated checks pass: source protection, second slot, marked
keys, XYZ alignment, quaternion rotation, Euler turns, locked channels,
comparison, recalculation, unused preview cleanup and atomic failure.

Version 1.1.0 adds **28 selection checks**: separate runs, boundaries, exact
preservation of unselected keys and handles, X-only selection, complete and
partial quaternions, empty selections, Graph Editor filters and sidebar, new
selection, recalculation, save and reopen. An additional test on the Mixamo
Swing Action reduces two sections on Hips and LeftForeArm while preserving
other keys and channels. Detailed reports and test scripts are included.

## Source code and license

The installation ZIP includes the complete Python source and Blender manifest.
Licensed under **GPL-3.0-or-later**; see LICENSE. No Maxon code is used.
This release is not affiliated with Maxon or the Blender Foundation.
