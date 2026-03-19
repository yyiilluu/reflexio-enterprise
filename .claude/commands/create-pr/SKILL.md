---
name: create-pr
description: "Create high-quality pull requests via gh pr create. Use when the user wants to create a PR, submit a PR, open a pull request, submit for review, or push changes for review. Triggers on: create a pr, create-pr, submit a pr, open a pull request, submit for review, make a pr, gh pr create."
---

# PR Creator

Create well-structured, reviewer-friendly pull requests following best practices.

**CRITICAL: This skill MUST always result in a PR being created. Do NOT stop early, do NOT ask the user to run another command first. Handle all prerequisites (committing, branching, pushing) inline and proceed to `gh pr create`.**

---

## Workflow

### Step 1: Pre-flight Checks

Run these checks before anything else:

1. **Verify GitHub CLI authentication** — run `gh api user --jq '.login'` to confirm the CLI is authenticated. If this fails, tell the user to run `gh auth login` first and stop.
2. **Determine the base branch** — default to `main`. If the user specifies a different base, use that. Capture as `$BASE_BRANCH`.

### Step 2: Commit Uncommitted Changes

Run `git status` to check for uncommitted changes. If there are uncommitted changes, run the `/commit` skill to commit them. This ensures all code quality checks (ruff, pyright, biome, tsc) and precommit hooks are applied consistently.

If there are no uncommitted changes, skip to Step 3.

### Step 3: Ensure Feature Branch

1. **Check current branch** — run `git branch --show-current`.
2. **If on `$BASE_BRANCH`**, create a feature branch:
   - Analyze the commits/changes to pick a descriptive name (e.g., `feat/add-auth`, `fix/login-bug`)
   - Run `git checkout -b <branch-name>`
3. **If on a different branch**, check whether the branch has PR-worthy commits vs `$BASE_BRANCH`:
   - Run `git log $BASE_BRANCH..HEAD --oneline`
   - If there are commits, use the current branch as-is
   - If there are NO commits (branch is at same point as base), this means something went wrong — investigate and fix

### Step 4: Sync with Base Branch

1. **Fetch latest** — run `git fetch origin $BASE_BRANCH`
2. **Check for divergence** — run `git log HEAD..origin/$BASE_BRANCH --oneline`
3. **Rebase if needed** — if the base branch has new commits:
   a. Run `git rebase origin/$BASE_BRANCH`
   b. If conflicts arise, surface them to the user — show both sides and ask which to keep. Do not silently resolve.
   c. After resolving, `git add <file>` and `git rebase --continue`

### Step 5: Push

Push the branch to remote:
```bash
git push -u origin HEAD
```
If the push is rejected (e.g., diverged history after rebase), use `git push --force-with-lease -u origin HEAD`.

### Step 6: Analyze Changes and Draft PR

1. **Analyze** — run these in parallel:
   - `git log $BASE_BRANCH..HEAD --oneline` — all commits
   - `git diff $BASE_BRANCH...HEAD --stat` — files changed summary
   - `git diff $BASE_BRANCH...HEAD` — full diff
2. **Check PR size** — if >500 lines changed, warn the user but continue.
3. **Draft title** — under 70 characters, conventional prefix (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`).
4. **Draft body** using this template:

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

Guidelines:
- Explain *why*, not just *what*
- For WIP PRs, use the `--draft` flag instead of `[WIP]` prefix
- Include Mermaid diagrams when they clarify workflows or architecture
- Do NOT include any "Generated with Claude Code" footer or bot attribution
- Do NOT include `Co-Authored-By` lines

### Step 7: Create the PR

Write body to a temp file and create the PR:

```bash
cat > /tmp/pr_body.md <<'EOF'
## Summary
...

## Changes
...

## Test Plan
...
EOF
gh pr create --title "the pr title" --base $BASE_BRANCH --body-file /tmp/pr_body.md
```

**Optional flags:**
- WIP/draft: add `--draft`
- Reviewers: add `--reviewer <handle>`
- Assignees: add `--assignee <handle>`

**Do NOT add:**
- `--author` flag (gh uses the authenticated user automatically)
- Any `Co-Authored-By` trailer
- Any "Generated with Claude Code" footer

### Step 7.5: Frontend UI Verification (when applicable)

If the PR includes frontend changes (`*.tsx`, `*.jsx` files under `reflexio/website/`), run automated UI verification using agent-browser:

1. **Detect frontend changes** — check if any files in the branch diff match `reflexio/website/**/*.{tsx,jsx}`:
   ```bash
   git diff $BASE_BRANCH...HEAD --name-only -- 'reflexio/website/**/*.tsx' 'reflexio/website/**/*.jsx'
   ```
   If no frontend files changed, skip this step.

2. **Ensure services are running** — check if the frontend is accessible:
   ```bash
   curl -sf http://localhost:${FRONTEND_PORT:-8080}/ > /dev/null 2>&1
   ```
   If not running, start services using the `/run-services` skill.

3. **Identify affected pages** — map changed files to routes:
   - `app/interactions/page.tsx` → `/interactions`
   - `app/profiles/page.tsx` → `/profiles`
   - `app/feedbacks/page.tsx` → `/feedbacks`
   - Other `app/**/page.tsx` → derive route from path

4. **Verify each affected page** — for each route:
   ```bash
   agent-browser open http://localhost:${FRONTEND_PORT:-8080}<route>
   agent-browser wait --load networkidle
   agent-browser snapshot -i
   agent-browser screenshot
   ```
   - Verify the page loads without errors (no error boundaries, no blank screens)
   - Verify key interactive elements are present in the snapshot
   - If the Test Plan section mentions specific UI behaviors for this page, verify them:
     - Change filter inputs and verify badges/indicators appear
     - Click buttons and verify dialogs open
     - Click cancel/close and verify no side effects
   - **Do NOT perform destructive actions** (delete, submit forms that modify data)

5. **Attach screenshots** — note the screenshot paths in the PR report so the user can add them to the PR.

### Step 8: Report

- Return the PR URL so the user can review it
- If `gh pr create` fails, diagnose the error and retry with fixes

---

## Best Practices

**Commit History:** If the commit history is messy, suggest rebasing to clean it up before creating the PR.

**Feedback Requests:** If the user mentions wanting specific feedback, add a "Feedback Requested" section to the body.

**Screenshots:** For frontend changes, remind the user to add screenshots or recordings to the PR after creation.
