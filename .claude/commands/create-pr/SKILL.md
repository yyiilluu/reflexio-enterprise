---
name: create-pr
description: "Create high-quality pull requests via gh pr create. Use when the user wants to create a PR, submit a PR, open a pull request, submit for review, or push changes for review. Triggers on: create a pr, create-pr, submit a pr, open a pull request, submit for review, make a pr, gh pr create."
---

# PR Creator

Create well-structured, reviewer-friendly pull requests following best practices.

---

## Workflow

### Step 1: Pre-flight Checks

Run these checks before anything else:

1. **Verify GitHub CLI authentication** — run `gh api user --jq '.login'` to confirm the CLI is authenticated. If this fails, the user needs to run `gh auth login` first.
2. **Verify clean git state** — run `git status` to ensure no uncommitted changes. If there are uncommitted changes, run the `/commit` skill first to commit them (this handles precommit hooks, README updates, API doc updates, and AI instruction file syncing). If the `/commit` skill is not available, manually stage and commit the changes before proceeding.
3. **Determine the base branch** — default to `main`. If the user specifies a different base, use that. Capture as `$BASE_BRANCH` and use consistently in all subsequent steps.
4. **Ensure you are on a feature branch** — if currently on `main` (or the base branch), create a feature branch first:
   - Pick a descriptive branch name (e.g., `feat/short-description`)
   - Run `git checkout -b <branch-name>`
   - If there are commits on `main` that should be in the PR, they are already on the new branch (it forked from `main`). After creating the PR, optionally reset `main` back to `origin/main` to keep it clean.
5. **Check remote tracking** — verify the current branch tracks a remote and is pushed up-to-date. If not, push with `-u` flag.
6. **Sync submodules** — check if `.gitmodules` exists first. If it does, run `git submodule update --init --recursive`. If not, skip this step.

### Step 2: Sync with Base Branch

Ensure the feature branch is up-to-date with the base branch to avoid merge conflicts in the PR:

1. **Fetch latest remote** — run `git fetch origin $BASE_BRANCH`
2. **Check for divergence** — run `git log HEAD..origin/$BASE_BRANCH --oneline` to see if the base branch has new commits
3. **Rebase if needed** — if there are new commits on the base branch:
   a. If there are uncommitted changes, stash them first: `git stash`
   b. Run `git rebase origin/$BASE_BRANCH`
   c. **Resolve conflicts** — if the rebase hits conflicts:
      - Read the conflicting files to understand both sides
      - Surface the conflict to the user — show both sides and ask which version to keep. Do not silently resolve conflicts.
      - Stage resolved files: `git add <file>`
      - Continue: `git rebase --continue`
      - Repeat until rebase completes
   d. If changes were stashed, pop them: `git stash pop`
      - If the stash pop conflicts, resolve those too
4. **Verify clean state** — run `git status` to confirm no unresolved conflicts remain

### Step 3: Analyze Changes

Understand the full scope of changes that will be in the PR:

1. Run `git log $BASE_BRANCH..HEAD --oneline` to see all commits on this branch
2. Run `git diff $BASE_BRANCH...HEAD --stat` for a high-level summary of changed files
3. Run `git diff $BASE_BRANCH...HEAD` to read the full diff
4. **Check PR size** — check total lines changed. If >500 lines, warn the user that the PR is large and suggest splitting before continuing to draft.
5. Identify the type of change: `feat`, `fix`, `refactor`, `docs`, `chore`, etc.

**Important:** Look at ALL commits, not just the latest one.

### Step 4: Draft the PR

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
- For work-in-progress PRs, use the `--draft` flag (see Step 5) rather than prefixing the title with `[WIP]`
- Include Mermaid diagrams when they simplify explanation of workflows or architecture
- Keep PRs focused on a single concern — suggest splitting if the PR is too large
- Do NOT include any "Generated with Claude Code" footer or bot attribution lines
- Do NOT include `Co-Authored-By` lines

### Step 5: Create the PR

Write the body to a temp file and use `--body-file` to avoid shell argument length limits:

```bash
cat > /tmp/pr_body.md <<'EOF'
## Summary
...

## Changes
...

## Test Plan
...
EOF
gh pr create --title "the pr title" --body-file /tmp/pr_body.md
```

**Optional flags:**
- If the user indicates this is a WIP or draft PR, add the `--draft` flag.
- If the user specifies reviewers, add `--reviewer <handle>` (comma-separated for multiple).
- If the user specifies assignees, add `--assignee <handle>`.

**Do NOT add:**
- `--author` flag (gh uses the authenticated user automatically)
- Any `Co-Authored-By` trailer
- Any "Generated with Claude Code" footer

### Step 6: Report

- Return the PR URL so the user can review it
- If `gh pr create` fails, diagnose the error and suggest fixes

---

## Best Practices Encoded

**Commit History:** If the commit history is messy, suggest rebasing to clean it up before creating the PR. Clean commits that explain *why* make review much easier.

**Feedback Requests:** If the user mentions wanting specific feedback, add a "Feedback Requested" section to the body.

**Screenshots:** For frontend changes, remind the user to add screenshots or recordings to the PR after creation.
