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

**Story Rule Set**:
The immutable ordered authoring rules compiled for the Theme and Frame stages
of one story run. Built-in rules define only stage semantics and universal
contracts; optional rules from `story-inputs/rules/` add reusable project
policy. The resolved set is frozen with the run and reused on resume.
_Avoid_: Story Description, Prompt Generation rules, per-input special case

**Story Description Authority**:
The rule that medium, layout, regions, views, scale systems, visual hierarchy,
and other subject-specific presentation behavior live in the Story Description
rather than Python branches. The story compiler understands stages and schema,
not named input archetypes.
_Avoid_: Brief-type detection, story-input adapter

**Story Content Level**:
The requested visible-content floor for every Narrative Frame: `aesthetic`,
`erotic`, or `hardcore`. It changes authoring instructions, never the adult
consent safety contract. Only the selected level is compiled into provider
prompts.
_Avoid_: Legacy Content Level, safety mode

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
input; prompt-file runs retain it as generation metadata but name output from
the Source Prompt Stem.
_Avoid_: Run name, Theme title, source prompt stem

**Source Prompt Stem**:
The input prompt filename without its extension, frozen in the Story Request.
For prompt-file runs it is the first part of the published filename, before
content level and numeric female and male counts.
_Avoid_: Full prompt path, Story Semantic Name

**Cast Slug**:
A deterministic lowercase English snake_case rendering of the requested
female and male totals for direct Story Description input. Prompt-file outputs
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
title, premise, and concise style phrase that identifies the event, character
tension, decisive moment, and visual mode. Differences between Narrative
Themes come from story events rather than prop, color, or camera substitutions.
The premise is a bounded story seed, not a scene-by-scene action list.
_Avoid_: Legacy Theme, variant label

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
Together they form a micro-story while each frame remains independently
understandable.
_Avoid_: Review cycle, storyboard schema

## Standalone Spatial Prompt Generation

The `t2i_spatial_prompt` package is independent from both Prompt Generation
and Standalone Story Generation. Do not reuse their stages, persistence, or
provider configuration.

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

**Spatial Prompt**:
One independently renderable final prompt compiled from geometry and Scene
Layers. A batch passes only when every prompt and all batch diversity
thresholds pass local validation.
_Avoid_: Narrative Frame, test output
