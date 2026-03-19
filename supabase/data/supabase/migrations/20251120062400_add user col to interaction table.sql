alter table "public"."interactions" add column "role" text not null default 'User'::text;
