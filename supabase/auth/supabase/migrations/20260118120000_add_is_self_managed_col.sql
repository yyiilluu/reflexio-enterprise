-- Add is_self_managed column to organizations table
-- When true, deployment migrations will skip this organization

alter table "public"."organizations" add column "is_self_managed" boolean not null default false;
