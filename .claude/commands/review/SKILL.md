---
name: review
description: Rigorous code review of all uncommitted changes. Analyzes architecture, code quality, security, and engineering best practices. Asks clarifying questions when intent is unclear, then summarizes all proposed changes as a plan for user approval before any edits are made.
---

# Code Review

Perform a rigorous, senior-engineer-level code review of all uncommitted changes in the working tree.

## Core Principles

- **You are a strict reviewer, not a rubber-stamper.** Flag real problems. Do not praise code just to be nice.
- **Never make changes directly.** Your output is a review report and an optional change plan. Wait for explicit user approval before editing any file.
- **Ask questions when intent is ambiguous.** If you cannot tell whether something is intentional or a mistake, ask.
- **Focus on substance over style.** Formatting issues caught by pre-commit hooks are low priority. **Ruff lint violations and pyright type errors in changed files are substantive findings** — classify them by severity alongside manual review findings.

## Workflow

### Phase 1 — Gather the diff

Run these commands to understand the full scope of uncommitted work:

```bash
# Overview of changed files
git status

# Full diff of all tracked changes (staged + unstaged)
git diff HEAD

# List of untracked files that may need review
git ls-files --others --exclude-standard
```

Read the diff carefully. For every changed file, also read the **full file** (not just the diff hunk) so you understand the surrounding context — imports, class hierarchy, sibling functions, and call sites.

**Run automated lint and type checks on changed Python files:**
```bash
# Get changed Python files
git diff HEAD --name-only -- '*.py'

# Run ruff on changed files only
ruff check <changed .py files>

# Run pyright on changed files only
pyright <changed .py files>
```
Save the ruff and pyright output — these results feed into the review checklist below.

### Phase 2 — Understand context

For each changed file:

1. Read the file's component-level `README.md` if one exists (e.g., `reflexio/server/README.md`).
2. Identify the module's responsibility and how it fits into the overall architecture.
3. If the change touches an interface consumed by other modules (API schema, service base class, client method), find and read the consumers.
4. If tests are changed, read the application code under test. If application code is changed, check whether corresponding tests exist and whether they cover the new behavior.

### Phase 3 — Review checklist

Evaluate every change against the following categories. Only report findings that are **actionable** — skip categories where everything looks correct.

#### 3.1 Correctness & Logic
- Are there off-by-one errors, wrong comparisons, or logic inversions?
- Are edge cases handled (empty inputs, None/null, zero-length collections, boundary values)?
- Do conditional branches cover all expected states?
- Are return types consistent with what callers expect?
- Is async/await used correctly (no missing awaits, no blocking calls in async context)?

#### 3.2 Architecture & Design
- Does the change follow existing patterns in the codebase? If it deviates, is the deviation justified?
- Are responsibilities placed in the right layer (API route vs. service vs. utility)?
- Is there unnecessary coupling between modules that should be independent?
- Are new abstractions justified, or do they add complexity without benefit?
- Does the change violate separation of concerns?
- If a new service/extractor/endpoint is added, does it follow the established pattern?

#### 3.3 API & Contract Design
- Are request/response schemas complete and correct?
- Are field names consistent with existing conventions?
- Are optional vs. required fields set correctly?
- Are default values sensible?
- Is backward compatibility preserved where needed?
- Are enums used where a fixed set of values is expected?

#### 3.4 Security
- Is user input validated and sanitized before use?
- Are there SQL injection, command injection, or XSS risks?
- Are secrets or credentials hardcoded or logged?
- Are authorization checks in place for protected endpoints?
- Is sensitive data exposed in error messages or logs?
- Are file paths validated to prevent path traversal?

#### 3.5 Error Handling & Resilience
- Are exceptions caught at the right level (not swallowed silently, not leaking implementation details)?
- Are error messages actionable for the caller?
- Are external service failures handled gracefully (LLM calls, database, third-party APIs)?
- Is retry logic appropriate and bounded?
- Are resources cleaned up on failure (connections, file handles)?

#### 3.6 Type Safety & Data Integrity
- Review pyright output from Phase 1. All type errors in changed files are findings — classify by severity.
- Are type hints present and correct on new/changed functions?
- Are Pydantic models used where structured validation is needed?
- Are there implicit type coercions that could cause subtle bugs?
- Are Optional types handled with proper None checks?
- Are union types narrowed before use?

#### 3.7 Performance
- Are there N+1 query patterns or unnecessary database round-trips?
- Are there large allocations or copies that could be avoided?
- Is pagination used for list endpoints?
- Are there blocking calls in async code paths?
- Is work being repeated that could be cached or deduped?

#### 3.8 Testing
- Do new features have corresponding tests?
- Do bug fixes include a regression test?
- Are tests testing behavior (not implementation details)?
- Are test assertions specific enough to catch regressions?
- Are mocks set up correctly (not masking real bugs)?
- Do tests cover both happy-path and error cases?

#### 3.9 Missing Critical Test Cases
Go beyond checking whether tests exist for the *changed* code. Proactively identify **core logic in the changed files** that lacks test coverage, even if the logic was not modified in this diff. Focus on:

- **Security-sensitive code paths** — input validation, auth checks, path traversal guards, injection defenses. If these are untested, flag them as Significant.
- **Pure functions and utilities** — functions with clear inputs/outputs that are easy to unit test but have no tests.
- **Branching logic with edge cases** — functions with multiple `if`/`else` branches, especially error/fallback branches that are easy to miss.
- **Data transformation and serialization** — code that converts between formats (e.g., DB rows to API responses, file parsing). Incorrect transformations cause subtle bugs.
- **Integration points** — API endpoints, file I/O, external service calls. Even if mocked, the request/response contract should be tested.

For each gap found, suggest specific test cases with descriptive names (e.g., `test_get_conversation_rejects_path_traversal`) and briefly describe what the test should verify. Group suggestions by priority (security first, then correctness, then edge cases).

#### 3.10 Code Duplication & DRY Violations
Duplicated code is one of the biggest threats to long-term maintainability. When the same logic exists in multiple places, bug fixes and feature changes must be applied everywhere — and inevitably some copies get missed, creating inconsistencies and regressions.

**Actively search for duplication.** Do not limit yourself to the diff — when you see a pattern in the changed code, search the broader codebase for similar implementations. Use grep/search to find:

- **Copy-pasted functions or methods** — Functions in different files/classes that do the same thing with minor variations (different variable names, slightly different parameters, same core logic). Flag these even if only one copy is in the diff.
- **Repeated code blocks within a file** — Multiple places in the same file that perform the same sequence of operations (e.g., identical error handling, identical data transformation steps, identical validation logic).
- **Parallel class hierarchies or services** — Multiple services/extractors/handlers that implement near-identical workflows with only the "content" differing. These should typically share a base class or utility.
- **Duplicated constants, prompts, or configuration** — The same string literals, magic numbers, or config structures defined in multiple places. A change to one copy without updating the others causes silent divergence.
- **Near-duplicate data models or schemas** — Pydantic models, TypeScript interfaces, or database schemas that represent the same concept with slightly different field names or types.
- **Repeated conditional logic** — The same `if`/`else` decision tree appearing in multiple places, especially feature-flag checks or permission checks.

For each duplication found:
1. Identify **all** copies (not just the two most obvious ones).
2. Note the **differences** between copies — are they meaningful or accidental?
3. Suggest a concrete consolidation strategy: extract a shared function, create a base class, use a configuration-driven approach, etc.
4. Classify as **Significant** if the duplication spans multiple files or involves logic that is likely to change together. Classify as **Minor** if it is localized and low-risk.

#### 3.11 Code Clarity & Maintainability
- Are variable and function names descriptive and consistent with codebase conventions?
- Is complex logic explained with a comment about *why* (not *what*)?
- Are there dead code paths, unreachable branches, or leftover debug code?
- Are magic numbers or strings extracted into named constants?

#### 3.12 Frontend (when applicable)
- Are components following the project's ShadCN + Tailwind patterns?
- Is state management appropriate (server state vs. client state)?
- Are loading and error states handled in the UI?
- Is the UI consistent with existing pages?
- Are accessibility basics covered (labels, keyboard navigation)?

### Phase 4 — Ask clarifying questions

If during the review you encounter any of the following, **stop and ask the user before proceeding**:

- Intent is ambiguous — you cannot tell if something is a deliberate design choice or a mistake.
- A change conflicts with patterns documented in README files.
- A breaking change to a public interface may have been unintentional.
- A test is removed or weakened and it is unclear whether this is deliberate.
- New dependencies are added with no obvious justification.

Use the `AskUserQuestion` tool to ask focused, specific questions. Batch related questions together (up to 4 per round).

### Phase 5 — Produce the review report

Output a structured review report using this format:

```
## Code Review Summary

**Files reviewed:** <count>
**Scope:** <one-line description of what the changes do>

### Critical Issues (must fix)
Items that would cause bugs, security vulnerabilities, or data loss.
- [ ] **[FILE:LINE]** — Description of the issue and why it matters.

### Significant Issues (should fix)
Items that degrade code quality, violate architecture, or hurt maintainability.
- [ ] **[FILE:LINE]** — Description and recommendation.

### Minor Issues (nice to fix)
Items that are low-risk but would improve the code.
- [ ] **[FILE:LINE]** — Description and suggestion.

### Duplication Issues
Code that is duplicated across files or within files, hurting maintainability.
- [ ] **[FILE1:LINE] ↔ [FILE2:LINE]** — Description of what is duplicated and suggested consolidation approach.

### Missing Critical Test Cases
Core logic that lacks test coverage. Prioritized by risk (security > correctness > edge cases).
- [ ] `test_name_here` — What the test should verify and why it matters.

### Lint & Type Check Results
Ruff and pyright findings on changed files.
- [ ] **[FILE:LINE]** `RULE_CODE` — Description and fix recommendation.

### Observations
Things that are not wrong but worth noting (e.g., "this module is growing large — consider splitting in the future").

### What looks good
Briefly note well-implemented aspects (1-3 bullet points max). Do not over-praise.
```

### Phase 6 — Propose change plan (if issues found)

If there are Critical or Significant issues, produce a concrete change plan:

```
## Proposed Changes

### Change 1: <short title>
**File:** <path>
**Issue:** <which review finding this addresses>
**What to change:** <specific description of the modification>

### Change 2: <short title>
...
```

Then explicitly ask the user:
> "Here is my review and proposed changes. Should I proceed with all changes, some of them, or none?"

**Do NOT make any edits until the user approves.**

## Severity Definitions

| Severity | Definition | Action |
|----------|-----------|--------|
| **Critical** | Will cause bugs, data loss, security vulnerability, or crash in production | Must fix before commit |
| **Significant** | Violates architecture, creates tech debt, missing error handling, missing tests | Should fix before commit |
| **Minor** | Naming, clarity, minor duplication, small improvements | Nice to have, can defer |
| **Observation** | Not a problem today but worth tracking | No action needed now |

## What This Review Does NOT Cover

- **Formatting and whitespace** (handled by pre-commit hooks and ruff format)
- **Import ordering** (handled by ruff `I` rules)
- Line length (handled by linters)
- Whether the feature itself is a good idea (that is a product decision, not a code review)
