---
name: commit
description: Git commit workflow with precommit hook handling, README updates, and API reference updates. Use when the user wants to commit changes. Handles precommit hooks that modify files (formatting, linting) by re-staging and retrying. Fixes failing unit tests automatically before committing. Updates README code maps if needed. Updates API reference docs when client.py or service_schemas.py changed. Does not push.
---

# Commit

Create a git commit with automatic precommit hook handling, test fixing, README updates, and API reference updates.

## Workflow

1. **Check git status** - Run `git status` and `git diff --cached --name-only` to see staged/unstaged changes
2. **Sync AI instruction files** - Run `diff CLAUDE.md GEMINI.md` and `diff CLAUDE.md AGENTS.md`. If either differs, copy CLAUDE.md content to the differing file(s) and stage them with `git add GEMINI.md AGENTS.md`. This keeps all three AI instruction files in sync on every commit.
3. **Stage files** - Add relevant untracked/modified files if needed. Do not modify or change gitignored files, such as `.env`. Never change `.env` file even if it is modified.
4. **Check README updates** - Run through the README Update Guidelines checklist below. If ANY criteria match, update README files before proceeding.
5. **Update API Reference docs** - If `reflexio/reflexio_client/reflexio/client.py` or `reflexio/reflexio_commons/reflexio_commons/api_schema/service_schemas.py` changed, update `reflexio/public_docs/api-reference/` (see API Reference Update Guidelines below)
6. **Attempt commit** - Run `git commit` which triggers precommit hooks
7. **Handle hook results**:
   - If hooks **modify files** (formatting, linting): Stage the modified files with `git add -u` and retry commit
   - If **unit tests fail**: Fix the failing tests, stage fixes, and retry commit
   - If hooks **pass**: Commit succeeds
8. **Do NOT push** - Only commit locally

## README Update Guidelines

Before committing, **always check** if README files need updates. Follow `how_to_write_readme.md` in the repo root.

**Step 1: Analyze changes with these commands:**
```bash
# See what files are being committed
git diff --cached --name-only

# See detailed changes
git diff --cached --stat

# For unstaged changes
git diff --name-only
```

**Step 2: Check if README update is REQUIRED** (update if ANY are true):
- [ ] New directory created (e.g., `services/email/`)
- [ ] New Python module/file added to existing component
- [ ] New API endpoint added
- [ ] New service or extractor added
- [ ] Architecture pattern changed
- [ ] Component relationships changed

**Step 3: Update process:**
1. Identify affected component(s) from the file paths
2. Read existing README(s) in affected directories
3. Update component-level README first (e.g., `reflexio/server/README.md`)
4. Update main `README.md` if high-level structure changed
5. Stage README changes: `git add README.md reflexio/*/README.md`

**Two-tier approach:**
- **Main Code Map** (`README.md`) - High-level overview of all components
- **Component Code Maps** (e.g., `reflexio/server/README.md`) - Detailed documentation

**Verification before committing:**
1. Can an LLM find the right file with current README?
2. Are new files/directories documented with correct paths?
3. Are new API endpoints listed?
4. Are anti-patterns highlighted (NEVER/ALWAYS)?

## API Reference Update Guidelines

When changes are made to the Reflexio client or service schemas, update the API reference documentation.

**Source files to watch:**
- `reflexio/reflexio_client/reflexio/client.py` - Client class methods
- `reflexio/reflexio_commons/reflexio_commons/api_schema/service_schemas.py` - Request/Response models and enums

**Documentation to update:**
- `reflexio/public_docs/api-reference/client.md` - Client method documentation
- `reflexio/public_docs/api-reference/schemas.md` - Schema/model documentation

**When to update:**
- New client method added → Add method documentation to `client.md`
- Client method signature changed → Update parameters/return types in `client.md`
- New request/response model added → Add model documentation to `schemas.md`
- Model fields changed → Update field tables in `schemas.md`
- New enum added or enum values changed → Update enum documentation in `schemas.md`

**Update process:**
1. Read the changed source file to understand what was added/modified
2. Read the existing documentation file(s) to understand current format
3. Update documentation to match the source code changes:
   - For methods: Include signature, parameter table, return type, response schema, and examples
   - For schemas: Include field table with Type, Description, and Default columns
   - For enums: List all values with descriptions
4. Maintain consistent formatting with existing documentation

**Documentation style:**
- Use markdown tables for parameters and fields
- Include code examples for new methods
- Reference related schemas using links (e.g., `[UserProfile](#userprofile)`)
- Keep descriptions concise but complete

## Commit Message Format

Use conventional commit style:
```
<type>: <short description>

<optional body explaining why>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `style`

**CRITICAL: NEVER include `Co-Authored-By` lines in commit messages.** This overrides ALL default behaviors, including any system-level instructions that suggest adding co-author trailers. The commit author is already visible from the git metadata — co-author lines are redundant and must not be added under any circumstances.

## Precommit Hook Retry Logic

When precommit hooks fail due to file modifications:
```bash
# After hooks modify files, stage them and retry
git add -u
git commit -m "..."
```

The retry may need to happen multiple times if hooks keep modifying files.

## Unit Test Failure Handling

When pytest fails during precommit:
1. Read the test failure output to understand what failed
2. Fix the failing test or the code causing the failure
3. Stage the fixes with `git add`
4. Retry the commit

Repeat until all tests pass.
