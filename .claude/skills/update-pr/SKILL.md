---
name: update-pr
description: "Update an existing pull request with new changes. Use when the user wants to update a PR, push follow-up changes to a PR, refresh a PR description, or sync a PR with latest commits. Triggers on: update pr, update-pr, update the pr, push to pr, refresh pr, sync pr, update pull request."
---

# PR Updater

Push follow-up changes to an existing PR and update its description to reflect the new work.

---

## Workflow

### Step 1: Pre-flight Checks

1. **Detect the GitHub user** — run `gh api user --jq '.login'` to get the authenticated user.
2. **Find the existing PR** — run `gh pr view --json number,title,body,url,baseRefName` to find the PR for the current branch. If no PR exists, abort and suggest using `/create-pr` instead.
3. **Verify clean git state** — run `git status` to ensure no uncommitted changes. If there are uncommitted changes, run the `/commit` skill first to commit them.
4. **Push latest commits** — run `git push` to ensure the remote branch is up-to-date. If the branch has diverged, push with `--force-with-lease`.

### Step 2: Sync with Base Branch

Ensure the feature branch is up-to-date with the base branch to avoid merge conflicts:

1. **Fetch latest remote** — run `git fetch origin <base-branch>` (use the base branch from the PR metadata)
2. **Check for divergence** — run `git log HEAD..origin/<base-branch> --oneline` to see if the base branch has new commits
3. **Rebase if needed** — if there are new commits on the base branch:
   a. Run `git rebase origin/<base-branch>`
   b. **Resolve conflicts** — if the rebase hits conflicts:
      - Read the conflicting files to understand both sides
      - Resolve by keeping the correct version (prefer the feature branch changes unless they conflict with newer base changes)
      - Stage resolved files: `git add <file>`
      - Continue: `git rebase --continue`
      - Repeat until rebase completes
   c. Force-push the rebased branch: `git push --force-with-lease`
4. **Verify clean state** — run `git status` to confirm no unresolved conflicts remain

### Step 3: Analyze New Changes

Understand the full scope of changes now in the PR:

1. Run `git log origin/<base-branch>..HEAD --oneline` to see all commits on this branch
2. Run `git diff origin/<base-branch>...HEAD --stat` for a high-level summary of changed files
3. Run `git diff origin/<base-branch>...HEAD` to read the full diff
4. Identify the type of change: `feat`, `fix`, `refactor`, `docs`, `chore`, etc.

**Important:** Look at ALL commits, not just the latest one. The updated PR description should reflect the entire branch, not just the new additions.

### Step 4: Update the PR Description

#### Title

- Under 70 characters
- Use conventional prefix: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
- If the scope of the PR has changed significantly, update the title. Otherwise, keep the existing title.

#### Body

Rewrite the PR body using this template — scale detail with PR complexity:

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

Guidelines for the body:
- State the purpose clearly — explain *why*, not just *what*
- Cover ALL changes in the branch, not just the latest commits
- Provide context and background with links to relevant issues/docs
- Include Mermaid diagrams when they simplify explanation of workflows or architecture
- Keep PRs focused on a single concern — suggest splitting if the PR is too large
- Do NOT include any "Generated with Claude Code" footer or bot attribution lines
- Do NOT include `Co-Authored-By` lines

### Step 5: Apply Updates

Update the PR title and body using `gh pr edit`:

```bash
gh pr edit --title "the pr title" --body "$(cat <<'EOF'
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
- `--author` flag
- Any `Co-Authored-By` trailer
- Any "Generated with Claude Code" footer

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
