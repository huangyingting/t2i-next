# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all
operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`.
- **Read an issue**: `gh issue view <number> --comments`, including labels.
- **List issues**: use `gh issue list` with appropriate `--label`, `--state`,
  and JSON filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`.
- **Apply or remove labels**: use `gh issue edit <number> --add-label "..."`
  or `--remove-label "..."`.
- **Close an issue**: `gh issue close <number> --comment "..."`.

Infer `huangyingting/t2i-next` from the current repository remote.

## Pull requests as a triage surface

**PRs as a request surface: no.**

GitHub shares one number space across issues and pull requests. Resolve an
ambiguous `#<number>` with `gh pr view <number>` and then fall back to
`gh issue view <number>`.

## Skill operations

- When a skill says **publish to the issue tracker**, create a GitHub issue.
- When a skill says **fetch the relevant ticket**, run
  `gh issue view <number> --comments`.

## Wayfinding operations

The map is one issue labelled `wayfinder:map`, with child issues as tickets.

- Child ticket labels use `wayfinder:<type>` where type is `research`,
  `prototype`, `grilling`, or `task`.
- Prefer GitHub sub-issues and native issue dependencies. If unavailable, use
  a task list in the map and a `Blocked by: #<number>` line in the child.
- Claim work with `gh issue edit <number> --add-assignee @me`.
- Resolve work by commenting with the answer, closing the issue, and adding a
  short decision pointer to the map.
