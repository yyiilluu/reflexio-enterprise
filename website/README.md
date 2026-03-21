# /user_profiler/reflexio/website
Description: Next.js frontend for viewing user profiles and interactions

## Main Entry Points

- **Root**: `app/page.tsx` - Landing page
- **Layout**: `app/layout.tsx` - App layout with sidebar navigation
- **Login**: `app/login/page.tsx` - User authentication page
- **Register**: `app/register/page.tsx` - User registration page
- **Profiles**: `app/profiles/page.tsx` - View and search user profiles
- **Interactions**: `app/interactions/page.tsx` - View conversation history
- **Feedbacks**: `app/feedbacks/page.tsx` - View and manage user feedback
- **Evaluations**: `app/evaluations/page.tsx` - View agent success evaluation results
- **Skills**: `app/skills/page.tsx` - View and manage generated skills (gated by `skill_generation` feature flag)
- **Settings**: `app/settings/page.tsx` - Configuration and settings management

## Purpose

1. **Authentication** - User login and registration (skipped in self-host mode)
2. **Profile viewing** - Display extracted user profiles with search
3. **Interaction browsing** - View conversation history, tool usage (tool name + inputs), and context
4. **Feedback management** - View and manage user feedback (displays blocking issues when present)
5. **Evaluation monitoring** - Track agent success metrics and analyze failures
6. **Skill management** - View, search, export, and manage generated skills (feature-flag gated)
7. **Settings configuration** - Manage application settings including root-level tool configuration (`tool_can_use`)
8. **API integration** - Sync client communicates with FastAPI backend

## Components

**Directory**: `components/`

Key files:
- `sidebar.tsx`: Navigation sidebar for switching between views (filters items by feature flags)
- `layout-content.tsx`: Authentication wrapper that handles auth routing and sidebar display
- `ui/`: ShadCN UI components (button, card, input, table, accordion, tabs, switch, etc.)
- `settings/`: Settings page section components (StorageConfigSection, AgentContextSection, ProfileExtractorsSection, AgentFeedbackSection, AgentSuccessSection, AdvancedSettingsSection, ExtractionParamsSection) and shared helpers (FieldLabel, PasswordInput, TagManager, WindowOverrideFields)

## Feature Flags

**File**: `lib/auth-context.tsx`

Feature flags are returned from the login API and stored in localStorage (`reflexio_feature_flags`). The `AuthContext` exposes `isFeatureEnabled(name)` which returns `true` if the flag is not explicitly `false` (fail-open). In self-host mode, all features are enabled.

**Usage**:
- **Sidebar** (`components/sidebar.tsx`): Nav items with `featureFlag` property are hidden when the flag is disabled
- **Skills page** (`app/skills/page.tsx`): Shows lock screen when `skill_generation` is disabled

## Architecture Pattern

**Next.js App Router** - Uses React Server Components where possible
**ShadCN UI** - Consistent design system across pages
**Backend API** - Calls FastAPI server at `http://0.0.0.0:8081`

## Development

**Install dependencies (first time setup):**
```bash
npm install
```

**Start dev server:**
```bash
npm run dev
```
Open http://localhost:8080

**Build:**
```bash
npm run build
npm run start
```

## Styling

- **Tailwind CSS** - Utility-first styling
- **globals.css** - Global styles and CSS variables
- **ShadCN components** - Pre-styled, accessible components
