# Git Worktree Guide

Git worktree lets you check out multiple branches simultaneously in separate directories, so you can work on different features without stashing or committing incomplete work.

## Setup a New Worktree

```bash
# From your main repo at /Users/yilu/repos/reflexio

# Create a worktree for a feature branch
git worktree add ../reflexio-feature-x feature-x

# Or create a new branch in the worktree
git worktree add -b new-feature ../reflexio-new-feature main
```

This creates a new directory `../reflexio-feature-x` checked out to that branch. Each worktree is a full working directory sharing the same `.git` data.

## List / Remove Worktrees

```bash
git worktree list              # see all worktrees
git worktree remove ../reflexio-feature-x   # remove when done
git worktree prune             # clean up stale entries
```

## Working Across Worktrees

Each worktree is independent — you can build, test, and commit in each one separately:

```bash
# Terminal 1: main repo
cd /Users/yilu/repos/reflexio
# work on main branch

# Terminal 2: feature worktree
cd /Users/yilu/repos/reflexio-feature-x
# work on feature-x branch
```

**Important for this repo**: Each worktree needs its own environment setup:

```bash
cd ../reflexio-feature-x
uv sync
source .venv/bin/activate
```

## Merging Commits Between Worktrees

Since all worktrees share the same git history, merging is straightforward:

```bash
# Option 1: Merge from any worktree
cd /Users/yilu/repos/reflexio        # go to main worktree
git merge feature-x                   # merge the feature branch

# Option 2: Rebase
cd /Users/yilu/repos/reflexio-feature-x
git rebase main                       # rebase feature onto main

# Option 3: Cherry-pick specific commits
cd /Users/yilu/repos/reflexio
git cherry-pick <commit-hash>         # pick specific commits
```

## Key Rules

1. **No two worktrees can have the same branch checked out** — git enforces this
2. All worktrees share refs, so a commit made in one is visible in all others via `git log`
3. Don't delete worktree directories manually — use `git worktree remove` to keep git's internal state clean
4. Stashes are shared across all worktrees

## Typical Workflow

```bash
# 1. Create worktree for a feature
git worktree add -b feat/new-ui ../reflexio-new-ui main

# 2. Work in the worktree
cd ../reflexio-new-ui
# ... make changes, commit ...

# 3. Go back to main and merge
cd /Users/yilu/repos/reflexio
git merge feat/new-ui

# 4. Clean up
git worktree remove ../reflexio-new-ui
git branch -d feat/new-ui
```
