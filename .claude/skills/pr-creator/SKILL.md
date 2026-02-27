---
name: pr-creator
description: "Create high-quality pull requests via gh pr create. Use when the user wants to create a PR, submit a PR, open a pull request, submit for review, or push changes for review. Triggers on: create a pr, submit a pr, open a pull request, submit for review, make a pr, gh pr create."
---

# PR Creator

Create well-structured, reviewer-friendly pull requests following best practices.

---

## Workflow

### Step 1: Pre-flight Checks

Run these checks before anything else:

1. **Detect the GitHub user** — run `gh api user --jq '.login'` to get the authenticated user. Use this as the PR author. Do NOT hardcode any username.
2. **Verify clean git state** — run `git status` to ensure no uncommitted changes. If there are uncommitted changes, ask the user whether to commit first or proceed.
3. **Determine the base branch** — default to `main`. If the user specifies a different base, use that.
4. **Ensure you are on a feature branch** — if currently on `main` (or the base branch), create a feature branch first:
   - Pick a descriptive branch name (e.g., `feat/short-description`)
   - Run `git checkout -b <branch-name>`
   - If there are commits on `main` that should be in the PR, they are already on the new branch (it forked from `main`). After creating the PR, optionally reset `main` back to `origin/main` to keep it clean.
5. **Check remote tracking** — verify the current branch tracks a remote and is pushed up-to-date. If not, push with `-u` flag.

### Step 2: Analyze Changes

Understand the full scope of changes that will be in the PR:

1. Run `git log main..HEAD --oneline` to see all commits on this branch
2. Run `git diff main...HEAD --stat` for a high-level summary of changed files
3. Run `git diff main...HEAD` to read the full diff
4. Identify the type of change: `feat`, `fix`, `refactor`, `docs`, `chore`, etc.

**Important:** Look at ALL commits, not just the latest one.

### Step 3: Draft the PR

#### Title

- Under 70 characters
- Use conventional prefix: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
- Reference issue/ticket numbers when applicable (e.g., `feat: add user auth (#42)`)
- Short and scannable — put details in the body, not the title

#### Body

Use this template — scale detail with PR complexity:

```
## Summary
<1-5 bullet points explaining what changed and WHY>

## Changes
<Categorized list of what was modified — group by area/concern>

## Diagrams
<OPTIONAL — include Mermaid diagrams when visual aids clarify workflow or architecture changes>

## Test Plan
<How the changes were verified — manual testing steps, automated tests run, curl commands, etc.>
```

Guidelines for the body:
- State the purpose clearly — explain *why*, not just *what*
- Provide context and background with links to relevant issues/docs
- For work-in-progress PRs, prefix title with `[WIP]`
- Include Mermaid diagrams when they simplify explanation of workflows or architecture
- Keep PRs focused on a single concern — suggest splitting if the PR is too large
- Do NOT include any "Generated with Claude Code" footer or bot attribution lines
- Do NOT include `Co-Authored-By` lines

### Step 4: Create the PR

Run `gh pr create` using a HEREDOC for the body to preserve formatting:

```bash
gh pr create --title "the pr title" --body "$(cat <<'EOF'
## Summary
...

## Changes
...

## Test Plan
...
EOF
)"
```

**Do NOT add:**
- `--author` flag (gh uses the authenticated user automatically)
- Any `Co-Authored-By` trailer
- Any "Generated with Claude Code" footer

### Step 5: Report

- Return the PR URL so the user can review it
- If `gh pr create` fails, diagnose the error and suggest fixes

---

## Best Practices Encoded

**PR Size:** Keep PRs small and focused. If the diff is very large (>500 lines changed), suggest splitting into smaller PRs before creating.

**Commit History:** If the commit history is messy, suggest rebasing to clean it up before creating the PR. Clean commits that explain *why* make review much easier.

**Feedback Requests:** If the user mentions wanting specific feedback, add a "Feedback Requested" section to the body.

**Screenshots:** For frontend changes, remind the user to add screenshots or recordings to the PR after creation.
