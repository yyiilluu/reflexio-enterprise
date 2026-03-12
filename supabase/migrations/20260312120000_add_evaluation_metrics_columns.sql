ALTER TABLE "public"."agent_success_evaluation_result"
  ADD COLUMN "number_of_correction_per_session" integer DEFAULT 0,
  ADD COLUMN "avg_turns_to_resolution" integer,
  ADD COLUMN "is_escalated" boolean DEFAULT false;
