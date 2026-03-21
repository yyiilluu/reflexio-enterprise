---
name: update-pr
description: "Update an existing pull request with new changes. Use when the user wants to update a PR, push follow-up changes to a PR, refresh a PR description, or sync a PR with latest commits. Triggers on: update pr, update-pr, update the pr, push to pr, refresh pr, sync pr, update pull request."
---

# PR Updater

Push follow-up changes to an existing PR and update its description to reflect the new work.

---

## Workflow

### Step 1: Pre-flight Checks

1. **Verify GitHub CLI authentication** — run `gh api user --jq '.login'` to confirm the CLI is authenticated. If this fails, the user needs to run `gh auth login` first.
2. **Find the existing PR** — run `gh pr view --json number,title,body,url,baseRefName,state` to find the PR for the current branch. If no PR exists, abort and suggest using `/create-pr` instead. Check the `state` field — if it is not `OPEN`, abort and inform the user that the PR is already merged or closed.
3. **Verify clean git state** — run `git status` to ensure no uncommitted changes **in the enterprise repo**. If there are uncommitted changes, run the `/commit` skill first to commit them.

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

### Step 2: Sync with Base Branch

Ensure the feature branch is up-to-date with the base branch to avoid merge conflicts:

1. **Fetch latest remote** — run `git fetch origin <base-branch>` (use the base branch from the PR metadata)
2. **Check for divergence** — run `git log HEAD..origin/<base-branch> --oneline` to see if the base branch has new commits
3. **Rebase if needed** — if there are new commits on the base branch:
   a. Run `git rebase origin/<base-branch>`
   b. **Resolve conflicts** — if the rebase hits conflicts:
      - Read the conflicting files to understand both sides
      - Surface the conflict to the user — show both sides and ask which version to keep. Do not silently resolve conflicts.
      - Stage resolved files: `git add <file>`
      - Continue: `git rebase --continue`
      - Repeat until rebase completes
4. **Verify clean state** — run `git status` to confirm no unresolved conflicts remain
5. **Push the branch** — run `git push`. If the rebase changed history, use `git push --force-with-lease` instead. If `--force-with-lease` fails, it means someone else has pushed to this branch. Fetch the remote branch (`git fetch origin <branch>`), inspect the divergence (`git log HEAD..origin/<branch> --oneline`), and ask the user how to proceed — they may need to integrate the other contributor's changes first.

### Step 2.5: Update Submodule PR (if submodule has changes)

Skip this step if `$SUBMODULE_HAS_CHANGES` is false.

1. **`cd` into submodule**:
   ```bash
   cd open_source/reflexio
   ```

2. **Commit any uncommitted changes** — run `git status`. If there are uncommitted changes, stage and commit them (use ruff check/format for Python files, write a conventional commit message). **Do NOT include `Co-Authored-By` or any bot attribution lines.**

3. **Ensure feature branch** — check current branch with `git branch --show-current`. If on `main`, create a feature branch matching the enterprise branch name.

4. **Sync submodule branch** — `git fetch origin main && git rebase origin/main` (handle conflicts the same way as Step 2)

5. **Push submodule** — `git push` (or `--force-with-lease` if rejected after rebase)

6. **Check for existing submodule PR** — `gh pr view --json number,url,body 2>/dev/null`

7. **If PR exists — update it**:
   - Analyze new changes: `git log origin/main..HEAD --oneline`, `git diff origin/main...HEAD --stat`, `git diff origin/main...HEAD`
   - Use the same Phase A (append) + Phase B (holistic review) approach as the enterprise update-pr (Step 4)
   - Write updated body to temp file and apply:
     ```bash
     gh pr edit --title "..." --body-file /tmp/submodule_pr_body.md
     ```
   - Capture the submodule PR URL as `$SUBMODULE_PR_URL`

8. **If no PR exists — create one**:
   - Analyze changes: `git log main..HEAD --oneline` and `git diff main...HEAD --stat`
   - Draft title and body following the same template (Summary, Changes, Test Plan)
   - Add a "Related PRs" section: `## Related PRs\n- Enterprise PR: *(will be linked after creation)*`
   - Write body to temp file and create:
     ```bash
     gh pr create --title "..." --base main --body-file /tmp/submodule_pr_body.md
     ```
   - Capture the submodule PR URL as `$SUBMODULE_PR_URL`

9. **Return to enterprise root** — `cd` back to the enterprise repo root

10. **Stage submodule reference update**:
    ```bash
    git add open_source/reflexio
    ```
    If there are staged changes (the submodule pointer changed), commit:
    ```bash
    git commit -m "chore: update open_source/reflexio submodule reference"
    ```
    **Do NOT add `Co-Authored-By` or any bot attribution trailers to this commit.**

### Step 3: Analyze Changes (New + Full)

#### 3a: Identify new changes since last PR update

Determine what's changed since the PR description was last written/updated:

1. Run `git log origin/<current-branch>..HEAD --oneline` to find commits that haven't been pushed yet (local-only changes). If empty, the PR body may already be up-to-date — but still proceed to verify.
2. Compare the commits listed in the existing PR body against `git log origin/<base-branch>..HEAD --oneline` to identify commits not yet reflected in the description.
3. Run `git diff origin/<current-branch>..HEAD` to see the diff of only the new (unpushed) changes. This is what you'll use to append new content in Step 4 Phase A.

#### 3b: Full branch diff (for holistic review)

Understand the full scope of all changes in the PR:

1. Run `git log origin/<base-branch>..HEAD --oneline` to see all commits on this branch
2. Run `git diff origin/<base-branch>...HEAD --stat` for a high-level summary of changed files
3. Run `git diff origin/<base-branch>...HEAD` to read the full diff. Note: Three-dot (`...`) syntax is intentional — it shows only the changes introduced on this branch since it diverged from the base, excluding commits on the base branch that aren't part of this PR.
4. Identify the type of change: `feat`, `fix`, `refactor`, `docs`, `chore`, etc.

**Important:** Look at ALL commits, not just the latest one. The full branch diff is used for the holistic review in Step 4 Phase B.

#### 3c: Submodule changes (if applicable)

If `$SUBMODULE_HAS_CHANGES=true`, also analyze the submodule diff to include in the PR description:

```bash
git -C open_source/reflexio log origin/main..HEAD --oneline
git -C open_source/reflexio diff origin/main...HEAD --stat
```

Include a summary of submodule changes in the enterprise PR body (under the Changes section).

### Step 4: Update the PR Description

> **Do NOT rewrite the PR body from scratch.** Start from the existing body, add what's new, then refine. The existing description was reviewed and approved — preserve its content unless it's factually wrong or contradicted by new changes.

#### Phase A: Append new changes (incremental update)

1. **Read the existing PR body** from Step 1
2. **Identify what's already documented** — compare the existing Summary, Changes, and Test Plan against the new changes identified in Step 3a
3. **Add new content incrementally:**
   - Add new bullet points to **Summary** for new changes (don't rewrite existing bullets)
   - Add new entries to **Changes** section (don't reorganize or rephrase existing entries)
   - Add new test steps to **Test Plan** (don't remove existing steps)
4. **Preserve manually-added content** — any sections or content not matching the standard template (e.g., reviewer notes, deployment checklists, linked discussions, custom sections) must be preserved by default. Only remove content that directly contradicts the current code.
5. **Update Related PRs section** — if `$SUBMODULE_HAS_CHANGES=true`, ensure a `## Related PRs` section exists with a link to `$SUBMODULE_PR_URL`. If the section already exists, update the link if the URL changed.

#### Phase B: Holistic review (light refinement)

Re-read the full updated description (from Phase A) alongside the complete branch diff (from Step 3b):

1. **Check for redundancy** — merge duplicate bullets that describe the same change
2. **Check for contradictions** — remove or correct statements that contradict the current code
3. **Check for outdated items** — remove references to code/behavior that no longer exists in the branch
4. **Check for missing coverage** — if any significant changes from the full diff are not mentioned, add them
5. **Light coherence pass** — make minor wording adjustments so the description reads naturally as a whole, but do NOT restructure or rephrase content that is already accurate
6. **Check for over-promotion of intermediate steps** — Intermediate commits (reverts, temporary scaffolding, cleanup of earlier commits in the same PR) should not appear in the title or as standalone sections in the body. Fold them into the relevant primary change they support. The title and Summary should reflect the PR's overall purpose, not list every commit.

#### Title

- Under 70 characters
- Use conventional prefix: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
- Review the existing PR title (from Step 1). If it still accurately reflects the full scope of changes, **keep it unchanged**. Only update if the scope has materially changed or the title is misleading.
- The title should describe the PR's overall goal, not enumerate individual commits. Intermediate steps (reverts, temporary changes, cleanup) should not appear in the title.

#### Body template reference

The body should follow this structure — but when updating, work within the existing body rather than replacing it with this template:

```
## Summary
<1-5 bullet points explaining what changed and WHY — covering ALL changes in the branch>

## Changes
<Categorized list of what was modified — group by area/concern>

## Diagrams
<OPTIONAL — include Mermaid diagrams when visual aids clarify workflow or architecture changes>

## Related PRs
<ONLY if $SUBMODULE_HAS_CHANGES=true — link to the submodule PR>

## Test Plan
<How the changes were verified — manual testing steps, automated tests run, curl commands, etc.>
```

#### Guidelines
- State the purpose clearly — explain *why*, not just *what*
- Cover ALL changes in the branch, not just the latest commits
- Provide context and background with links to relevant issues/docs
- Include Mermaid diagrams when they simplify explanation of workflows or architecture
- Keep PRs focused on a single concern — suggest splitting if the PR is too large
- Do NOT include any "Generated with Claude Code" footer or bot attribution lines
- Do NOT include `Co-Authored-By` lines

### Step 5: Apply Updates

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
gh pr edit --title "the pr title" --body-file /tmp/pr_body.md
```

**Do NOT add:**
- `--author` flag
- Any `Co-Authored-By` trailer
- Any "Generated with Claude Code" footer

**Draft/Ready handling:** If the user wants to mark a draft PR as ready for review, run `gh pr ready`. If the user wants to convert to draft, run `gh pr ready --undo`.

### Step 5.1: Cross-link Submodule PR (if submodule has changes)

Skip this step if `$SUBMODULE_HAS_CHANGES` is false.

After updating the enterprise PR, update the submodule PR's body to link back:

```bash
# Get enterprise PR URL
ENTERPRISE_PR_URL=$(gh pr view --json url --jq '.url')
# Update submodule PR body to add the link
cd open_source/reflexio
EXISTING_BODY=$(gh pr view --json body --jq '.body')
```

- If the submodule PR body contains the placeholder `*(will be linked after creation)*`, replace it with the actual enterprise PR URL.
- If the submodule PR body already has a `## Related PRs` section, ensure the enterprise PR link is current.
- If neither exists, append a `## Related PRs` section with the enterprise PR link.

Write the updated body to a temp file and apply:
```bash
cat > /tmp/submodule_pr_body_updated.md <<EOF
$UPDATED_BODY
EOF
gh pr edit --body-file /tmp/submodule_pr_body_updated.md
cd ../..
```

### Step 5.5: Frontend UI Verification (when applicable)

If the PR includes frontend changes (`*.tsx`, `*.jsx` files under `website/`), run automated UI verification using agent-browser:

1. **Detect frontend changes** — check if any files in the branch diff match `website/**/*.{tsx,jsx}`:
   ```bash
   git diff origin/<base-branch>...HEAD --name-only -- 'website/**/*.tsx' 'website/**/*.jsx'
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

### Step 6: Report

- Return the PR URL so the user can review it
- Summarize what changed in the PR description compared to before
- If `gh pr edit` fails, diagnose the error and suggest fixes

---

## Best Practices Encoded

**PR Size:** Keep PRs small and focused. If the diff is very large (>500 lines changed), suggest splitting into smaller PRs.

**Commit History:** If the commit history is messy, suggest rebasing to clean it up. Clean commits that explain *why* make review much easier.

**Feedback Requests:** If the user mentions wanting specific feedback, add a "Feedback Requested" section to the body.

**Screenshots:** For frontend changes, remind the user to add screenshots or recordings to the PR after updating.
