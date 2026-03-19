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
3. **Verify clean git state** — run `git status` to ensure no uncommitted changes. If there are uncommitted changes, run the `/commit` skill first to commit them.
4. **Sync submodules** — check if `.gitmodules` exists first. If it does, run `git submodule update --init --recursive`. If not, skip this step.

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

#### Phase B: Holistic review (light refinement)

Re-read the full updated description (from Phase A) alongside the complete branch diff (from Step 3b):

1. **Check for redundancy** — merge duplicate bullets that describe the same change
2. **Check for contradictions** — remove or correct statements that contradict the current code
3. **Check for outdated items** — remove references to code/behavior that no longer exists in the branch
4. **Check for missing coverage** — if any significant changes from the full diff are not mentioned, add them
5. **Light coherence pass** — make minor wording adjustments so the description reads naturally as a whole, but do NOT restructure or rephrase content that is already accurate

#### Title

- Under 70 characters
- Use conventional prefix: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
- Review the existing PR title (from Step 1). If it still accurately reflects the full scope of changes, **keep it unchanged**. Only update if the scope has materially changed or the title is misleading.

#### Body template reference

The body should follow this structure — but when updating, work within the existing body rather than replacing it with this template:

```
## Summary
<1-5 bullet points explaining what changed and WHY — covering ALL changes in the branch>

## Changes
<Categorized list of what was modified — group by area/concern>

## Diagrams
<OPTIONAL — include Mermaid diagrams when visual aids clarify workflow or architecture changes>

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
