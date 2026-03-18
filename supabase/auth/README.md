# Login Database (Cloud Supabase)

This directory contains migrations for the cloud-hosted Supabase database used for user authentication and organization management.

## Architecture Overview

The application uses two separate Supabase databases:

| Database | Purpose | Location |
|----------|---------|----------|
| **Local Supabase** (`supabase/data/`) | User profiles, interactions, feedbacks, embeddings | `127.0.0.1:54321` |
| **Cloud Supabase** (`supabase/auth/`) | Organizations, login credentials, API keys | `*.supabase.co` |

## Setup Instructions

### 1. Create a Cloud Supabase Project

1. Go to [supabase.com](https://supabase.com) and sign in
2. Click "New Project" and fill in the details
3. Wait for the project to be provisioned

### 2. Get Your Credentials

1. In your Supabase project dashboard, navigate to **Settings → API**
2. Copy the following values:
   - **Project URL** (e.g., `https://abcdefg.supabase.co`)
   - **service_role key** (under "Project API keys" - the secret one, not anon)

### 3. Configure Environment Variables

Add these to your `.env` file:

```env
# Login Database (Cloud Supabase)
LOGIN_SUPABASE_URL=https://your-project-ref.supabase.co
LOGIN_SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...your-service-role-key
```

### 4. Run the Migration

#### Option A: Supabase SQL Editor (Recommended)

1. In your Supabase project dashboard, go to **SQL Editor**
2. Click "New query"
3. Copy and paste the contents of `migrations/001_create_organizations.sql`
4. Click "Run"

#### Option B: Supabase CLI

```bash
# Navigate to this directory
cd supabase/auth

# Initialize Supabase config (if not already done)
supabase init

# Link to your cloud project
supabase link --project-ref YOUR_PROJECT_REF

# Push migrations
supabase db push
```

## Verifying the Setup

After running the migration, you can verify the table was created:

1. Go to **Table Editor** in your Supabase dashboard
2. You should see the `organizations` table with these columns:
   - `id` (int4, primary key)
   - `created_at` (int4)
   - `email` (varchar, unique)
   - `hashed_password` (varchar)
   - `is_active` (bool)
   - `configuration_json` (text)
   - `api_key` (varchar)

## Connection Priority

The application connects to databases in this order:

1. **SELF_HOST=true** → In-memory SQLite (no auth needed)
2. **LOGIN_SUPABASE_URL + KEY set** → Cloud Supabase
3. **Fallback** → Local SQLite file (`reflexio/data/sql_app.db`)

## Security Notes

- The `service_role` key has admin access - keep it secret!
- Never expose `LOGIN_SUPABASE_KEY` in frontend code
- Row Level Security (RLS) is enabled on the organizations table
- The service role bypasses RLS for backend operations
