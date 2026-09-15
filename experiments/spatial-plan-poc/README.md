# Spatial-plan proof of concept

This isolated experiment does not modify or replace the story pipeline.

It performs one deterministic-plan validation:

1. Compile and validate a typed spatial plan from `scenario.json`.
2. Generate prose from the immutable valid plan.
3. Independently audit cast, camera, contact, visibility, limbs, and supports.

DeepSeek does not create or alter the spatial plan, character profiles,
settings, presentation plans, or visibility decisions. Final critical prose is
compiled deterministically; DeepSeek is used only for independent evaluation.

Run it from the repository root:

```bash
STORY_OPENAI_MODEL=DeepSeek-V3.2 uv run python experiments/spatial-plan-poc/run.py
```

Evidence is written under `output/`. A successful process exits with status 0
only when deterministic prose checks pass, a deliberately contradictory
visibility fixture is rejected, a tampered multi-camera/local-anatomy sentence
is rejected, and the six-part semantic audit passes.

Run the isolated eight-case diversity matrix:

```bash
STORY_OPENAI_MODEL=DeepSeek-V3.2 uv run python experiments/spatial-plan-poc/diversity.py
```

Its prompts and diversity metrics are written under `diversity-output/`.
DeepSeek drafts are retained separately for comparison, while final critical
geometry prose is compiled deterministically from each accepted plan.

Generate the five 256-entry multi-cast pose catalogs:

```bash
uv run python experiments/spatial-plan-poc/catalog_generator.py
```

The materialized catalogs and coverage manifest are written under `catalogs/`.
Persisted actor roles use lowercase codes (`f1`, `f2`, `f3`, `m1`, and `m2`).
Prompt-facing identities use stable uppercase labels such as `F1, woman 1` and
`M1, man 1`; personal names are not identity keys. Catalog schema 3.0 has one
actor identity system: `role`. Relationship edges use references such as
`focus_role`, `owner_role`, and `controller_role`; `pose_function` separately
describes a role's temporary geometric duty. Cast and focus membership are
stored once at their owning level rather than repeated in every pose and
activity. The superseded slot identity fields are not accepted or persisted.

Catalog schema 3.0 models controlled handheld vibrators and pelvis-mounted
strap-ons explicitly, including prop ownership, occupied hands, attachment
points, contact axes, and segmented visibility. Compiled scenes also include a
complete continuous-body ledger for every coded actor, bilateral limb chains
for supported lifts, and pelvis ownership for anatomical contact endpoints.

Run the deterministic catalog and compiled-prompt validation matrix:

```bash
uv run python experiments/spatial-plan-poc/catalog_validation.py
```

This validates all five catalogs and every compatible pose/activity pair,
checks all six representative scenes, and verifies that malformed prop,
contact, limb-ownership, restraint, and evaluation fixtures are rejected.
Evidence is written to `demo-output/validation-report.json`.

## Four-layer scene architecture

The current scene compiler uses four typed inputs and one deterministic
resolver:

1. `SpatialPlan` owns cast, pose, contact, support, occlusion, projection, and
   camera geometry.
2. `CharacterProfile` owns stable adult identity, stature, build, face, base
   hair, body-detail profile, grooming profile, and fantasy body traits.
3. `SettingPreset` owns world genre, location, era, time, weather,
   architecture, materials, environment props, motivated light sources,
   presentation biases, and exact-cast hazards.
4. `PresentationPlan` owns scene-local wardrobe, wardrobe state, footwear,
   accessories, makeup, hair styling, surface finish, lighting use, palette,
   and atmosphere.

[`scene_layers.py`](./scene_layers.py) defines these schemas, their independent
fingerprints, and the deterministic resolver. Final visibility is derived from
the spatial contacts, contact visibility, restraint regions, and wardrobe
state. It is not an independently generated layer. Body details are emitted
only for relevant regions that the spatial plan marks visible.

Resolver priority is fixed: adult constraints, exact cast and body continuity,
spatial contacts and supports, locked character identity, setting
compatibility, wardrobe and visibility, lighting, then atmosphere. Lower
layers cannot override higher-priority geometry.

Every setting must explicitly exclude background people, humanoid statues,
person-shaped shadows, and mirrors that show extra bodies. Lighting must use a
source declared by the selected setting. Wardrobe must be moved clear of every
required contact rather than changing the contact.

Layer prose has a hard 200-token estimate budget. The compiler deduplicates
shared wardrobe and makeup themes across roles, omits invisible body details,
and stores full typed data in `layers.json` instead of repeating it in the
prompt. Reports compare compact layer prose with verbose schema serialization.
The setting layer is deterministic, eliminating one model-generation call per
scene; DeepSeek is invoked only when `--evaluate` is requested. Evaluation
requests send the compiled prompt and scene ID only, because selections,
fingerprints, and layer JSON are redundant with the validation performed
locally.

The six-scene reference run compiles 4,382 estimated verbose layer tokens into
900 compact tokens, a 79% reduction, and avoids six style-generation calls.
For the twelve-scene second batch, removing redundant selection metadata from
the evaluation request reduced measured DeepSeek prompt usage from 8,947 to
5,451 tokens while retaining the complete compiled prompt.

Generate six representative scenes through deterministic geometry and layer
compilation, then independently evaluate them with DeepSeek:

```bash
STORY_OPENAI_MODEL=DeepSeek-V3.2 uv run python experiments/spatial-plan-poc/catalog_scene_demo.py
```

The combined prompts, resolved layers, token metrics, and evaluation are
written under `demo-output/`. The six presets include a rainy neon apartment,
an amber performance studio, a modern corridor, a midnight luxury hotel, a
soft morning bedroom, and a dark-fantasy demon palace. A run passes only when
all layer and geometry checks are clean and every independent evaluation
returns `pass`.

Generate twelve stratified pose-diversity prompts and evaluate them with
DeepSeek:

```bash
STORY_OPENAI_MODEL=DeepSeek-V3.2 uv run python \
  experiments/spatial-plan-poc/catalog_diversity_12.py --batch 1 --evaluate
```

The prompts, resolved layers, independent fingerprints, exact selections,
token metrics, 128-pose reference metrics, and evaluation are written under
`diversity-12-output/`. The reference subset uses eight variants from each of
all sixteen pose families. The twelve rendered tests must use twelve different
families, activities, and settings while covering all cast configurations, all
three body levels, all seven support surfaces, all six camera viewpoints, and
all three shot scales.

Generate the complementary second batch with the same coverage contract:

```bash
STORY_OPENAI_MODEL=DeepSeek-V3.2 STORY_OPENAI_TEMPERATURE=0 uv run python \
  experiments/spatial-plan-poc/catalog_diversity_12.py --batch 2 --evaluate
```

The second batch is written independently under
`diversity-12-round2-output/`; it does not overwrite the first batch. It
emphasizes the less-tested right-side lying, upright standing, bent standing,
elevated bridge, dual controlled props, BDSM, wall-supported group, and lifted
support topologies.
