# Agent instructions

## Before changing the project

- Start by understanding the problem, goal, scope, and workspace; clarify material uncertainties before choosing an approach.
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
- Update relevant documentation as you develop so it stays aligned with the implementation.
- Consider security, privacy, performance, and compatibility where they are relevant to the change.
- Use synthetic or sanitized test data. Never commit secrets, personal information, or production data.

## Required verification

- For every behavior change, add or update focused unit and regression tests for the changed behavior, edge cases, and affected callers.
- Run the full suite with `uv run --locked python -m unittest discover -v`, configured static checks, and an applicable smoke or system-level check covering the main data flow.
- Use synthetic data and mocks for hardware or external services. Run live integration checks only when available, safe, and free of sensitive user data capture.
- Review the full diff and affected files, then run `git diff --check` before finishing.
- Never silently skip a required check. Report which checks passed and explain any unavailable check and what remains unverified.
