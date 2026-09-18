# Prompt Generation

This context turns a creative brief into shared visual guidance, alternative
themes, and independently renderable frames.

## Language

**Brief**:
The user's semantic description of the desired subject, roles, action, and
setting.
_Avoid_: Prompt, request text

**Cast Plan**:
The run-wide semantic roster resolved from the Brief. It identifies each
person's role and gender, but contains no visual appearance or clothing.
_Avoid_: Character count, cast list

**Cast Constraint**:
An optional requested female or male total used to complete an ambiguous
Brief. It cannot override people explicitly described by the Brief.
_Avoid_: Character override

**Cast Default**:
One adult woman used only when the Brief and Cast Constraints leave the cast
undetermined. It is a fallback, not a constraint on an explicit cast.
_Avoid_: Default constraint

**Theme Character**:
A Theme-specific visual realization of one Cast Plan member, including stable
appearance, age, display label, and base outfit.
_Avoid_: Cast member

**Style Guide**:
The run-wide visual anchor and the range within which Themes may vary.
_Avoid_: Style, style option

**Theme**:
One complete visual interpretation of the Brief, with its own scene, look, and
Theme Characters.
_Avoid_: Scenario, style variant

**Frame**:
One independently renderable still image containing only currently visible
facts.
_Avoid_: Shot description, scene

## Standalone Story Generation

The `t2i_story_pipeline` package is independent from Prompt Generation above.
Do not reuse its Foundation, Theme, Frame, rules, persistence, or renderer.

**Story Description**:
The user's prose account of time, place, adult characters, relationships,
interaction, action, emotion, environment, camera intent, and lighting intent.
_Avoid_: Brief, configuration

**Story Document**:
The visual recipe input: a UTF-8 `.yaml` document containing an explicit ID,
natural-language visual facts, cast structure, stage/level visual refinements,
visual applicability, module references and catalog allocation. It contains no
generation, runtime, validation, policy-selection or safety-control settings.
Packaged visual prose is Chinese; the generated prose language is an independent
execution choice. Image text language and visual panel counts remain image facts.
_Avoid_: Run configuration, plain-text file input, executable workflow

**Story Run Configuration**:
The external generation, runtime and output-quality controls, supplied through
explicit JSON and CLI options rather than visual recipes or filename lookups.
Explicit CLI values override the supplied configuration, including zero;
unspecified gender counts use the recipe's visual cast. Program defaults do not
silently adapt to each recipe. The final request must satisfy visual applicability
and allocation contracts. The effective configuration is frozen with the resolved
input; resume does not rediscover its file or migrate older snapshot shapes.
_Avoid_: Recipe-specific shadow profile, safety switch, implicit directory lookup

**Story Rule Set**:
The immutable ordered authoring rules compiled for the Theme and Frame stages
of one story run. Built-in rules define only stage semantics and universal
contracts and mandatory safety; the program-selected standard-story policy owns
project defaults. Explicit modules
and Story Document authoring rules are selected for the current stage and level,
before the output-language rule. Shared level refinements have one source owner;
each stage receives its common rules, the shared selected-level refinements, and
its own selected-level instructions. The resolved set is frozen with the run and
reused on resume.
_Avoid_: Story Description, Prompt Generation rules, per-input special case

**Resolved Story Input**:
The validated, provider-independent compilation of one visual Story Document,
external run configuration and explicit overrides. It contains effective
generation/runtime/quality settings,
rules, source provenance, module contexts, and one plan per requested Theme.
It is frozen before generation and reloaded without source-file access on resume.
_Avoid_: Executable workflow, implicit working-directory configuration

**Story Input Module**:
A data-only reusable medium or layout capability selected explicitly by a
document, with bounded typed parameters, stage rules, and applicability.
Modules cannot load other modules or execute code.
_Avoid_: Plugin, generic prompt mixin, filename-specific branch

**Story Catalog Allocation**:
A deterministic mapping from program-owned Theme slots to catalog entries and
their stage-specific facts and cast requirements. Fixed-slot, alphabet-coverage,
and bounded cyclic-slot strategies do not change with provider batch boundaries
or retries. Conditional Frame assignments derive their view count from their slots and
preserve the original slot when only some Frames are retried. Correct
allocation is not a guarantee of generated geometry or visual quality.
_Avoid_: Model-selected counter, physical solver

**Story Cast Scope**:
The named participant group to which requested female/male counts apply.
Requested participants and fixed additional roles share the eight-principal
capacity. Explicit background population bands are accounted for separately
in total population ranges; they are not uncounted people or permission to
invent extras from prose. Repeated views of one identity do not add people.
_Avoid_: Hidden cast override, universal eight-person image limit

**Story Quality Policy**:
Externally declared output targets and local Theme/Frame evidence checks,
frozen in run settings rather than authored in visual recipes.
Unspecified defaults and explicit overrides retain distinct intent through typed,
dictionary and JSON forms. Resolved input freezes a concrete policy for each Theme
using its language and known principal count or lower bound; background populations
do not enlarge per-principal length targets. Explicit fixed bounds do not scale
merely because their numbers equal a default.
Each stage independently selects `off` to skip checks, `report` to record warnings
without quality retries, or `enforce` to reject failed output with bounded retries.
Theme checks target a named title, premise, or style field before the batch is
checkpointed or queued for Frame generation; Frame checks target final prose.
Basic schema, count, persistence, and safety contracts remain independent.
Applicable text constraints are projected into concrete writing targets using the
same stage and language applicability as validation. Disabling quality checks
does not erase configured output targets or mandatory safety. No model evaluator
is invoked.
_Avoid_: Safety switch, semantic guarantee, automatic review stage

**Story Quality Report**:
The result's separate Theme and Frame policy modes, `skipped`, `passed`, or
`warnings` statuses, and structured issues identifying the stage, field, check,
and Theme/Frame. Theme issues have no Frame ID. Attempt records keep historical
issues; the final report describes only accepted checkpoints and is verified
against the frozen policy on publication and completed-run loading.
_Avoid_: Hidden warnings, model score

**Story Description Authority**:
The rule that medium, layout, regions, views, scale systems, visual hierarchy,
and other subject-specific presentation behavior live in the Story Description
and explicit typed modules rather than filename branches. Descriptions cannot
override immutable schema, safety, selected system content-level boundaries,
or resolved numeric requirements.
_Avoid_: Brief-type detection, story-input adapter

**Story Content Level**:
The system-defined visible-content floor and limits for every Narrative Frame:
`aesthetic`, `erotic`, or `hardcore`. It changes authoring instructions, never the
adult consent safety contract. Only its resolved concrete constraints enter
provider prompts; the level identifier stays in configuration and frozen
provenance. Document or module refinements do not replace its definition.
_Avoid_: Legacy Content Level, safety mode

**Story Content-Level Refinement**:
A topic-specific requirement compatible with the selected system level.
Each level has one `authoring.level_refinements` entry, with `shared`, `themes`,
and `frames` responsibilities. Stage authoring outside this entry contains only
level-independent common rules. Shared requirements reach both stages directly rather than
depending on a generated Theme to restate them. Exact duplicate ownership is
invalid; this structural check is not a natural-language conflict detector.
Each branch's prose is self-contained for its selected level; grade-dependent
conditions belong in those branches, not descriptions or stage common rules.
Branches contain executable authoring requirements, not grade announcements or
compliance-proof headers. Repeated wording within one request can be removed,
but independently required Theme and Frame constraints must both reach the model.
_Avoid_: Level override, duplicated grade definition, shared reference-pool dump

**Nationality Default**:
Chinese nationality assigned independently to each person whose nationality
is not explicit in the Story Description. Setting, name, language, and
appearance are not nationality declarations.
_Avoid_: Ethnicity inference, setting inference

**Setting Default**:
China as the country containing the story setting when the Story Description
does not state a country or a place that identifies one. An unspecified
studio, room, or landscape is not permission to invent a foreign setting.
_Avoid_: Foreign setting invention, location inference

**Story Semantic Name**:
A short lowercase English snake_case name summarizing the whole Story
Description. It identifies published prompt files for direct Story Description
input; document runs retain it as generation metadata but name output from
the Source Prompt Stem.
_Avoid_: Run name, Theme title, source prompt stem

**Source Prompt Stem**:
The Story Document's explicit `id`, frozen as `source_prompt_stem` in the Story
Request. It is the first part of the published filename, before content level
and numeric female and male counts. Renaming the YAML file does not change it.
_Avoid_: Input filename, full prompt path, Story Semantic Name

**Cast Slug**:
A deterministic lowercase English snake_case rendering of the requested
female and male totals for direct Story Description input. Document outputs
instead include explicit numeric female and male count segments.
_Avoid_: Model-generated cast name, inferred cast

**Era Consistency**:
The requirement that every visible object, material, technology, garment,
title, and expression agree with the Story Description's time, place, and
social setting. Explicit time travel, alternate history, or intentional
anachronism in the Story Description overrides ordinary historical fidelity.
_Avoid_: Exact-date invention, silent modernization

**Narrative Theme**:
One micro-story concept derived from the Story Description. It owns a short
title, a complete stable premise, and an actionable visual direction appropriate
to its medium, without a fixed sentence quota, plus a compact diversity signature.
The model submits these fields
without an ID; the program assigns the Narrative Theme ID. Differences between Narrative
Themes come from story events rather than prop, color, or camera substitutions.
The premise is a bounded story seed, not a scene-by-scene action list.
_Avoid_: Legacy Theme, variant label

**Theme Diversity Signature**:
A compact account of the Theme's subject relationships, setting, visible
situation, and distinguishing visual design, generated alongside its full prose.
Every accepted signature remains in subsequent Theme prompts; only the two most
recent full Themes are repeated. Full Theme checkpoints remain authoritative for
Frame generation and resume. Matching signatures or matching premise/style text
are rejected deterministically, but different wording is not proof of semantic
novelty. This is coverage memory, not a new generation or review stage.
_Avoid_: Truncated premise, rolling window that forgets older Themes, quality score

**Narrative Frame**:
One final, independently renderable prose paragraph. It naturally integrates
time and place, event-bearing environment, a complete restatement of every
visible adult character, a legible static relationship, physical state,
camera, and light in the order that reads most naturally. It has no fixed
sentence openings, mandatory causal formula, intermediate visual-specification
fields, evaluator, or renderer.
_Avoid_: Narrative Scene, Story Shot, structured prompt

**Narrative Sequence**:
The ordered one-to-six Narrative Frames belonging to one Narrative Theme.
They share stable Theme facts as parallel visual alternatives, rather than an
implicit chronological progression; each remains independently understandable.
_Avoid_: Review cycle, storyboard schema

**Story Frame Batch**:
One model text response containing exactly one `<FRAME>...</FRAME>` block for
each requested missing slot. The program owns IDs, validates each paragraph,
and checkpoints accepted frames individually. Retry and resume request only
missing slots with accepted frames as context. Ambiguous boundaries or a wrong
block count reject the whole response rather than guessing slot ownership.
_Avoid_: Structured Frame output, per-frame model call, renderer

## Standalone Spatial Pipeline

The `t2i_spatial_pipeline` package is independent from both Prompt Generation
and Standalone Story Generation, and does not import the Film Style pipeline.
Do not reuse their stages, persistence, or provider configuration. Its CLI,
catalogs, diagnostics, and run storage belong to the spatial package; only
the low-level `t2i_model_provider` transport is shared.

**Neutral Pose Reference Library**:
An offline library of clothed adult figure-study recipes, exposed through
`t2i-spatial poses`. It owns typed body, spine, pelvis/chest/head orientation,
silhouette, balance bias, resting side, limbs and support facts plus compatible
full-body cameras. Room axes govern pelvis/chest and camera directions;
anatomical sides govern limbs and support placement; gaze is head-relative and
negative space is image-frame-relative. Load-bearing prose is derived only from
support contacts, never from a second weight-distribution label. Side-lying
recipes include a headrest and a forward lower palm on the mat with its elbow
raised, not an arm hidden beneath the torso. Upright kneeling uses knees and toe
ends; floor sitting uses bent knees and both feet on the mat. Its 16
families contain 48 curated whole-body recipes, not a limb Cartesian product.
It does not use activity templates or change the existing generate/bulk catalog.
The code-generated library is the sole definition; JSON is an export, not a
second editable source.
_Avoid_: Activity catalog replacement, story pipeline stage

**Pose Geometry Kernel**:
The independent `t2i_pose_geometry` package imports no pipeline or provider.
It owns a synthetic articulated body with fixed bone lengths, explicit joint
bounds, volumetric collision proxies, and metre-based right/front/up world
coordinates. NumPy/SciPy implement kinematics and bounded static contact
solving; python-fcl supplies primitive collision queries. Analytic two-bone arm
seeds cover alternative elbow and hand orientations without changing lengths.
An independent validator checks joint bounds, finite surface contacts, normals,
self-collisions, object collisions and inter-actor collisions. Contact
declarations never exempt collisions; adjacent shapes only receive localized
joint-region allowances. Solver success alone cannot certify a pose. These
are synthetic proxy assumptions, not biomechanics, balance, friction, cloth,
finger-level anatomy or rendered-image validation.
`solve_scene` fits the contacts of all explicitly specified actors in one
bounded optimization, rebuilding both endpoints of every body contact on each
iteration. Every actor must have explicit variable selectors or an empty fixed
declaration. Furniture and body dimensions remain fixed. It records per-contact
distance/normal errors and always revalidates the complete scene, including
uninvolved actors. Convergence and collision validity are separate requirements;
search failure does not prove physical impossibility.
_Avoid_: Story dependency, dynamics simulator, anatomical safety certificate

**Reference Geometry**:
The spatial adapter turns each neutral recipe into a candidate actor and solid
furniture, fits contacts, and requires a passing independent report before
rendering reference text. Standard furniture is sized for the pose, not a
certificate for arbitrary real furniture. Canonical solutions may initialize
uniformly scaled bodies and furniture, including mat thickness, but every
scaled instance is revalidated. Failed candidates remain rejected with explicit
diagnostics, never a symbolic fallback. A scene exports body dimensions,
angles, objects, contact constraints, world joints, numerical tolerances and
the report; loading checks that this evidence matches the current recipe and
kinematics. Three-view diagnostic SVGs recompute validation and show actual
proxy volumes, including failed candidates with a nonzero CLI exit.
_Avoid_: Reused pass flag, solver convergence as validity, AI-rendered preview

**Reference Presentation**:
An offline neutral setting, palette, motivated lighting and finish recipe with
qualitative camera-space capacity and concrete support-surface realizations.
Each support declares height, extent and orientation; each pose declares its
anatomical placement. Scene selection and validation require fitting profiles,
not merely a matching surface name. These qualitative staging requirements
precede concrete geometric realization, not measured anthropometry or force
constraints. Chair seat and back must
resolve to the same chair object; a headrest requires a mat. A camera recipe owns
coherent lens/perspective/distance intent, full-body framing, focus, depth,
negative space and foreground treatment. Presentation cannot rewrite pose
geometry. Accessible contact boundaries must remain readable, while naturally
occluded undersides and crossed limbs need not be exposed. Facial detail needs
light and visibility as well as focus; a complete silhouette cannot supply it.
_Avoid_: Unconstrained cinematic adjectives, physical optics simulation

**Reference Subject**:
A curated adult identity, explicitly authored uniform proxy-body scale, and
opaque full-coverage everyday outfit, repeated in every independently
renderable scene of a batch. Scale is not inferred from demographic traits.
The batch fixes one subject;
textual identity consistency is not a guarantee of rendered-image identity.
_Avoid_: Per-scene identity randomization

**Pose Reference Batch**:
A seed-reproducible, duplicate-free sample of neutral recipes with compatible
cameras, presentations, a fixed subject and locally rendered clothed reference
descriptions. Selection fixes the subject and rejects failed geometry before
balancing within-batch family counts, preferring
historically underused poses, then maximizing nearest structural distance,
measured as the equal-weight mismatch rate over eight geometry groups.
Camera/presentation combinations are selected only after support placement,
height/extent/orientation, head/view-sector and space compatibility checks.
Labels, gaze, identity and camera changes do not count as
pose-structure changes. Reports describe symbolic coverage, prior usage, pair
distances, checked geometry and explicit geometry rejections; they do not certify
rendered-image diversity, physical equilibrium or anatomical safety. Current
schema and renderer are version 4, with `geometry_gated_family_maximin_v4`
selection. Reports retain full physical/visual validation as false and require
render review; a passing static-proxy report has narrower meaning. No
image-generation backend is provided by this offline module.
_Avoid_: Perceptual score, visually validated pose

**Reference Usage Snapshot**:
An immutable, catalog-fingerprint-bound set of cumulative pose, camera,
presentation and complete-combination counts embedded before and after each
reference batch. CLI history continues a previous current-schema JSON batch
without modifying it; exact reproduction requires the same seed, library,
input snapshot, subject and filters. Concurrent continuations branch rather
than overwriting shared history. Text exports cannot resume usage, and changed
catalog definitions, geometry implementation, numerical dependency versions or
old schemas fail rather than resetting or migrating.
_Avoid_: Global mutable history file, seed-only reproducibility

**Spatial Audit**:
An offline, resumable check of packaged catalogs against current code-generated
definitions, retained topology constraints, deterministic scene allocation,
and compiled geometry. Every seed is replayed before its successful result
and structural diagnostics are checkpointed together. Audit checkpoints bind
both packaged data and generated definitions; incompatible schemas require
an explicit restart rather than migration.
Compiled geometry here is symbolic prose, not a numerical scene certificate.
Partner stance and body-continuity descriptions must agree with their supports;
the two actors in a bilateral lift cannot also control handheld props. This
restriction does not reserve the hands of an uninvolved third actor. A vertically
raised leg cannot also contribute to the declared planted-foot support.
Side-relative arm reservations resolve
to anatomical left/right hands before contact tasks are assigned; explicit
contact hands and tool grips take precedence over unspecified hand choices.
Compilation and topology validation share this hand allocation.
Surface contact and projected overlap are not themselves impossible poses. Solid
penetration requires geometric evidence, and unmodeled deformation or anatomy
remains unverified rather than receiving an automatic pass or rejection.
Bulk checkpoints also bind topology and prompt-audit versions, rejecting stale
batches before reuse; changed rules require a new run directory, not migration.
_Avoid_: Render validation, visual quality score

**Structural Diagnostics**:
Counts of selected catalog entries, detailed and macro structural signatures,
camera/shot and geometry coverage, and exact selection repetitions. Macro
signatures describe catalog body orientation, supports, and actor layout;
detailed signatures additionally include limb configurations and roles.
Within-batch pair counts are separate from accumulated cross-batch coverage.
These diagnostics are symbolic evidence, not text similarity or rendered-image
perceptual distance, and do not change scene selection.
_Avoid_: Perceptual fingerprint, visual diversity guarantee

**Creative Brief**:
The user's natural-language direction for the spatial batch's world, era,
atmosphere, and visual presentation. It does not prescribe catalog IDs.
_Avoid_: Brief, Story Description

**Creative Blueprint**:
The single model-derived Character, World, Style, and Presentation design
space shared by a twelve-scene batch. It contains one reusable adult
character-design slot for each role required by the batch's requested cast
configurations. Cast selection, pose, contact, and camera geometry remain
deterministic local constraints.
_Avoid_: Foundation, Narrative Theme

**Character Design Profile**:
The model-derived physical identity for one reusable F1, F2, F3, M1, or M2
slot: adult age, nationality, height, weight, build, proportions, skin, face,
hair style and color, intimate anatomy, pubic-hair design, and fantasy traits.
Profiles are independently designed and remain stable across the batch.
_Avoid_: Cast selection, shared default person

**Scene Request**:
One deterministic selection of cast configuration, pose family and variant,
activity, viewpoint, and shot scale. The released design builds twelve Scene
Requests from the packaged catalogs for a cast and seed.
_Avoid_: Frame, Narrative Frame

**Spatial Plan**:
The validated catalog entry and compatible activity selected for one Scene
Request. It owns body endpoints, support surfaces, contact edges, reachability,
and restraint topology.
_Avoid_: Creative Blueprint, prose prompt

**Scene Layers**:
The resolved character, setting, style, presentation, and expression facts
combined with a Spatial Plan. Each layer has one owner and a stable
fingerprint.
_Avoid_: Story Theme, Foundation

**Role Coverage Mode**:
The model-derived `selective_access` or `styled_nude` state for one visible
role in one presentation recipe. Roles in the same scene may use different
states, and no batch-wide nudity quota overrides the Creative Brief.
_Avoid_: Scene-wide wardrobe state, fixed nudity ratio

**Spatial Prompt**:
One independently renderable final prompt compiled from geometry and Scene
Layers. A batch passes only when every prompt and all batch diversity
thresholds pass local validation.
_Avoid_: Narrative Frame, test output
