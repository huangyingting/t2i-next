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

**Story Content Level**:
The requested visible-content floor for every Narrative Frame: `aesthetic`,
`erotic`, or `hardcore`. It changes authoring instructions, never the adult
consent safety contract. Only the selected level is compiled into provider
prompts.
_Avoid_: Legacy Content Level, safety mode

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
visible adult character, one static pose and one decisive action with visible
response and physical result, then an explicit camera sentence and light
sentence. It has no intermediate visual-specification fields and needs no
renderer.
Its setup states identity, goal, deadline, and consequence as static causal
facts; new evidence and relationship changes occur only in the decisive action.
_Avoid_: Narrative Scene, Story Shot, structured prompt

**Narrative Sequence**:
The ordered one-to-six Narrative Frames belonging to one Narrative Theme.
Together they form a micro-story while each frame remains independently
understandable.
_Avoid_: Review cycle, storyboard schema

**Quality Feedback**:
Non-blocking diagnostics for a Narrative Theme or Narrative Frame. It records
prompt-quality deviations in the Story Result for evaluation and future prompt
improvement, but never rejects or revises generated prose. Schema, identity,
count, and safety failures remain hard contract errors instead.
_Avoid_: Quality gate, review stage, revision request
