# Agent instructions

## Before changing the project

- Read this file and inspect the relevant code, configuration, and existing tests before acting.
- Gather the information needed to understand the task. Ask the user about unresolved choices that materially affect behavior or design; infer routine details from the repository and state important assumptions.
- Before writing code, understand the current design and outline responsibilities, interfaces, and data flow. Choose the simplest structure that keeps responsibilities cohesive; use object-oriented boundaries when they make the design clearer.
- Keep this `AGENTS.md` to 50 lines or fewer. There is no arbitrary line limit for source files; split files when it improves cohesion, readability, or reuse.
- Inspect the working tree before editing. Preserve unrelated user changes and avoid modifying files outside the task's scope.

## Python and dependencies

- Use `uv` for Python environments, dependency management, and project commands. Do not use `pip` directly.
- Keep `pyproject.toml` and `uv.lock` consistent when dependencies change; use `uv` to update the lockfile.

## Code quality

- Prefer clear names, small functions, explicit interfaces, and straightforward control flow. Avoid duplication and premature abstractions.
- Handle expected failures at the boundary where they can be explained or recovered from. Do not silently swallow errors.
- Add comments to explain intent, constraints, or non-obvious decisions; avoid comments that merely restate the code.
- Consider security, privacy, performance, and compatibility where they are relevant to the change.
- Use synthetic or sanitized test data. Never commit secrets, personal information, or production data.

## Review and verification

- Every code change must have unit tests and smoke or system-level coverage appropriate to its behavior. Add or update tests as needed, then run both levels before considering the work complete.
- Review the changes after implementation. For large edits, review the full diff and affected files for correctness, edge cases, unintended scope, and consistency with the design before testing.
- Keep changes focused, follow existing conventions, and update relevant documentation when behavior or setup changes.
- Report what changed and which checks passed. If a required check cannot run, explain why and what remains unverified.
