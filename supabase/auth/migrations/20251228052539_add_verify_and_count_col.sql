alter table "public"."organizations" add column "interaction_count" integer not null default 0;

alter table "public"."organizations" add column "is_verified" boolean not null default false;
