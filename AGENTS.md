# Codex working instructions

## Product direction

- Keep the extension's user interface, tooltips and errors in English. Maintain English and French user guides.
- Prioritize interactive preview in the Graph Editor. Read PROJECT_BRIEF.md before changing scope.
- The current source is the released 1.1.1 baseline. Preview is planned, not shipped. Do not describe planned behavior as available.
- Preserve extension ID `keyframe_reducer` and existing `kr.*` operator/property compatibility unless a documented migration is implemented.
- Keep this repository separate from the portfolio website and Marionette Workflow Helper.

## Data protection and animation correctness

- Keep the source Action unchanged. Recalculate from an immutable source, never repeatedly simplify the previous preview.
- Empty selection must never fall back to the whole Action. Preserve disjoint runs, their endpoints, outside handles, unselected channels and unrelated slots.
- Quaternion reduction must consider orientation and all WXYZ components. Preserve full Euler turns. Do not apply scalar tolerances to angular data without explicit conversion.
- Preserve unsupported/modified/locked channels or explain an explicit supported conversion. Keep atomic failure behavior.
- Do not claim continuous or world-space guarantees from local sampled checks. Foot-contact protection is a separate future feature.
- Maintain persistent comparison state and the dependency-order reload fix for in-session updates.
- Never save over a user's production .blend file in a test. Use copied or generated fixtures and isolated Blender profiles.

## Implementation and validation

- Keep `core.py` independent of bpy. Separate scheduling/preview state from numerical reduction.
- Do not use Python worker threads to read or mutate bpy data. Interactive work must respect Blender's main-thread context.
- Make the next preview implementation debounced, cancellable, deterministic and explicit about Apply/Cancel behavior.
- Run the relevant suites with `scripts/run_tests.py`; use all suites before a release. Add behavior-level regressions for meaningful changes, especially selection, undo, cancellation and reload.
- Keep historical fixture ZIPs immutable. Add a new fixture only when testing an actual released migration.
- `scripts/build_release.py` must remain portable, dependency-free and version-driven. Keep `bl_info`, manifest and release documentation consistent when intentionally bumping a version.
- Generated logs, profiles, builds and caches belong under ignored `build/` or `dist/`.
- Do not commit private production scenes, credentials or machine-specific absolute paths.
- Do not publish releases or deploy the website without task authorization. A local build or test does not imply publication.

## Communication

- Report what changed, why, the relevant tests and any remaining limitation.
- Keep terminology understandable to animators. Treat Maya/Cinema 4D as workflow references, not proof of algorithmic equivalence.
