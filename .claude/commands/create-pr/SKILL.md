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
2. **Determine the base branch** — ALWAYS use `main` as the base branch unless the user explicitly specifies a different base. Do NOT infer the base branch from the current branch's upstream, the repository default, or any other source. Capture as `$BASE_BRANCH`.

### Step 1.5: Detect Submodule Changes

Check if the `open_source/reflexio` submodule has changes that need a separate PR:

1. **Check for uncommitted changes in submodule**:
   ```bash
   git -C open_source/reflexio status --porcelain
   ```
2. **Check for unpushed commits in submodule**:
   ```bash
   git -C open_source/reflexio log --oneline origin/main..HEAD 2>/dev/null
   ```
3. If either command produces output, set `$SUBMODULE_HAS_CHANGES=true`. Otherwise `false`.
4. If `$SUBMODULE_HAS_CHANGES=true`, store the submodule path: `$SUBMODULE_PATH=open_source/reflexio`

### Step 2: Commit Uncommitted Changes

Run `git status` to check for uncommitted changes **in the enterprise repo** (excluding the submodule — submodule changes are handled in Step 2.5). If there are uncommitted changes, run the `/commit` skill to commit them. This ensures all code quality checks (ruff, pyright, biome, tsc) and precommit hooks are applied consistently.

If there are no uncommitted changes, skip to Step 2.5.

### Step 2.5: Create Submodule PR (if submodule has changes)

Skip this step if `$SUBMODULE_HAS_CHANGES` is false.

Process the submodule as a mini create-pr workflow:

1. **Commit submodule changes** — `cd` into `$SUBMODULE_PATH`:
   ```bash
   cd open_source/reflexio
   ```
   Run `git status`. If there are uncommitted changes, stage and commit them
   (use ruff check/format for Python files, write a conventional commit message).

2. **Create/reuse feature branch in submodule**:
   - Check current branch: `git branch --show-current`
   - If on `main`, create a feature branch with a name matching the enterprise work
     (e.g., if enterprise branch is `feat/add-search`, use `feat/add-search` in submodule too)
   - If already on a feature branch, reuse it

3. **Sync with base** — `git fetch origin main && git rebase origin/main` (handle conflicts the same way as Step 4)

4. **Push submodule branch** — `git push -u origin HEAD` (or `--force-with-lease` if rejected)

5. **Check for existing submodule PR** — `gh pr view --json number,url 2>/dev/null`

6. **Create submodule PR** (if none exists):
   - Analyze changes: `git log main..HEAD --oneline` and `git diff main...HEAD --stat`
   - Draft title and body following the same template as the enterprise PR (Summary, Changes, Test Plan)
   - Add a placeholder "Related PRs" section:
     ```
     ## Related PRs
     - Enterprise PR: *(will be linked after creation)*
     ```
   - Write body to a temp file and create:
     ```bash
     gh pr create --title "..." --base main --body-file /tmp/submodule_pr_body.md
     ```
   - Capture the submodule PR URL as `$SUBMODULE_PR_URL`

   **If PR already exists**: capture its URL as `$SUBMODULE_PR_URL` from the `gh pr view` output.

7. **Return to enterprise root** — `cd` back to the enterprise repo root

8. **Stage submodule reference update**:
   ```bash
   git add open_source/reflexio
   ```
   If there are staged changes (the submodule pointer changed), commit:
   ```bash
   git commit -m "chore: update open_source/reflexio submodule reference"
   ```

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
2. **If `$SUBMODULE_HAS_CHANGES=true`**, also analyze the submodule diff to include in the PR description:
   ```bash
   git -C open_source/reflexio log origin/main..HEAD --oneline
   git -C open_source/reflexio diff origin/main...HEAD --stat
   ```
   Include a summary of submodule changes in the PR body (under Changes section).
3. **Check PR size** — if >500 lines changed, warn the user but continue.
4. **Draft title** — under 70 characters, conventional prefix (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`). The title should describe the PR's overall goal, not enumerate commits. Omit intermediate steps (reverts, temporary scaffolding, cleanup of earlier commits in the same branch).
5. **Draft body** using this template:

```
## Summary
<1-5 bullet points explaining what changed and WHY>

## Changes
<Categorized list of what was modified — group by area/concern>

## Diagrams
<OPTIONAL — include Mermaid diagrams when visual aids clarify workflow or architecture changes>

## Related PRs
<ONLY if $SUBMODULE_HAS_CHANGES=true — link to the submodule PR>

## Test Plan
<How the changes were verified — manual testing steps, automated tests run, curl commands, etc.>
```

Guidelines:
- Explain *why*, not just *what*
- Distinguish primary changes from intermediate steps. Intermediate commits (reverts of earlier mistakes, temporary scaffolding, cleanup) should be folded into the section they support, not given their own top-level section. The Summary bullets should reflect the PR's purpose, not mirror the commit list.
- For WIP PRs, use the `--draft` flag instead of `[WIP]` prefix
- Include Mermaid diagrams when they clarify workflows or architecture
- Do NOT include any "Generated with Claude Code" footer or bot attribution

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

**If `$SUBMODULE_HAS_CHANGES=true`**: include a `## Related PRs` section in the body with a link to `$SUBMODULE_PR_URL`.

**Optional flags:**
- WIP/draft: add `--draft`
- Reviewers: add `--reviewer <handle>`
- Assignees: add `--assignee <handle>`

**Do NOT add:**
- `--author` flag (gh uses the authenticated user automatically)
- Any "Generated with Claude Code" footer

### Step 7.1: Cross-link Submodule PR (if submodule has changes)

Skip this step if `$SUBMODULE_HAS_CHANGES` is false.

After creating the enterprise PR, update the submodule PR's body to link back:

```bash
# Get enterprise PR URL
ENTERPRISE_PR_URL=$(gh pr view --json url --jq '.url')
# Update submodule PR body to add the link
cd open_source/reflexio
EXISTING_BODY=$(gh pr view --json body --jq '.body')
# Replace placeholder with actual link
UPDATED_BODY=$(echo "$EXISTING_BODY" | sed "s|Enterprise PR: .*(will be linked after creation).*|Enterprise PR: $ENTERPRISE_PR_URL|")
cat > /tmp/submodule_pr_body_updated.md <<EOF
$UPDATED_BODY
EOF
gh pr edit --body-file /tmp/submodule_pr_body_updated.md
cd ../..
```

### Step 7.5: Frontend UI Verification (when applicable)

If the PR includes frontend changes (`*.tsx`, `*.jsx` files under `website/`), run automated UI verification using agent-browser:

1. **Detect frontend changes** — check if any files in the branch diff match `website/**/*.{tsx,jsx}`:
   ```bash
   git diff $BASE_BRANCH...HEAD --name-only -- 'website/**/*.tsx' 'website/**/*.jsx'
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

### Step 8: Verify and Report

1. **Verify base branch** — run `gh pr view --json baseRefName --jq '.baseRefName'` to confirm the PR targets `$BASE_BRANCH` (should be `main` unless user specified otherwise). If it targets the wrong branch, fix it immediately:
   ```bash
   gh pr edit --base main
   ```
2. **Return the PR URL** so the user can review it
3. If `gh pr create` fails, diagnose the error and retry with fixes

---

## Best Practices

**Commit History:** If the commit history is messy, suggest rebasing to clean it up before creating the PR.

**Feedback Requests:** If the user mentions wanting specific feedback, add a "Feedback Requested" section to the body.

**Screenshots:** For frontend changes, remind the user to add screenshots or recordings to the PR after creation.
