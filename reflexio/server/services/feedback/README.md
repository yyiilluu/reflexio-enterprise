# /reflexio/server/services/feedback
Description: Feedback extraction, aggregation, deduplication, and skill generation pipeline

## Main Entry Points

- **Service Orchestrator**: `feedback_generation_service.py` - Manages feedback extraction lifecycle (regular, rerun, manual modes)
- **Feedback Extractor**: `feedback_extractor.py` - Extracts raw feedback from interactions via LLM
- **Feedback Aggregator**: `feedback_aggregator.py` - Clusters similar raw feedbacks and generates aggregated insights
- **Feedback Deduplicator**: `feedback_deduplicator.py` - Merges duplicate feedbacks from multiple extractors using LLM
- **Skill Generator**: `skill_generator.py` - Generates rich skills from clustered feedbacks enriched with interaction context

## Supporting Files

| File | Purpose |
|------|---------|
| `feedback_service_constants.py` | Prompt IDs for all feedback/skill operations |
| `feedback_service_utils.py` | Request dataclasses, Pydantic output schemas, message construction utilities |

## Architecture

### Data Flow

```
Interactions
  -> FeedbackExtractor (per-extractor, parallel)
    -> FeedbackDeduplicator (optional, if multiple extractors)
      -> RawFeedback (with optional blocking_issue) -> Storage
        -> FeedbackAggregator (manual trigger)
          -> Feedback (aggregated insights) -> Storage
        -> SkillGenerator (manual or auto trigger after aggregation)
          -> Skill (enriched with interaction context) -> Storage
```

### Feedback Extraction (`feedback_extractor.py`)

Extends `BaseGenerationService` extractor pattern. Each extractor:
1. Checks stride threshold before running
2. Constructs messages from interactions (via `service_utils.py`)
3. Runs LLM with `raw_feedback_extraction_main` prompt
4. Parses `StructuredFeedbackContent` output (do_action, do_not_action, when_condition, blocking_issue)
5. Saves `RawFeedback` to storage

**Tool Analysis**: Reads `tool_can_use` from root `Config` for tool usage analysis and blocking issue detection.

### Feedback Aggregation (`feedback_aggregator.py`)

Triggered manually via `/api/run_feedback_aggregation`. Clusters raw feedbacks and generates consolidated insights.

**Key Methods**:
- `get_clusters(raw_feedbacks, config)` - HDBSCAN/Agglomerative clustering on embeddings (reused by SkillGenerator)
- `aggregate()` - Full aggregation pipeline with LLM-based consolidation
- `_build_change_log()` - Builds `FeedbackAggregationChangeLog` with before/after snapshots (added/removed/updated feedbacks)

**Change Log**: After each aggregation, saves a `FeedbackAggregationChangeLog` to storage. In full_archive mode, all old feedbacks are "removed" and new ones "added". In incremental mode, maps old→new via fingerprints to detect updates. Saving is best-effort (failures logged, don't block aggregation).

**Clustering**: Embeds raw feedbacks → HDBSCAN clustering → falls back to Agglomerative if too few clusters

### Feedback Deduplication (`feedback_deduplicator.py`)

When multiple extractors produce overlapping feedback, deduplicates via LLM semantic matching. Uses `deduplication_utils.py` base class.

### Skill Generation (`skill_generator.py`)

Generates rich behavioral skills from raw feedback clusters, enriched with original conversation context.

**Key Design Decisions**:
1. **Interaction enrichment** - Fetches original interactions via `request_id` from raw feedbacks for conversation + tool usage context
2. **Conservative triggers** - Disabled by default, requires higher cluster thresholds, enforces cooldown between runs
3. **Clustering reuse** - Reuses `FeedbackAggregator.get_clusters()` for HDBSCAN clustering

**Class**: `SkillGenerator(llm_client, request_context, agent_version)`

**Key Methods**:
- `run(request)` - Main entry: check triggers → fetch feedbacks → cluster → generate/update skills → save
- `_should_run_generation()` - Cooldown check via `OperationStateManager` (service: `"skill_generator"`)
- `_collect_interaction_context()` - Fetch interactions by `request_id`, format with `format_interactions_to_history_string()`
- `_generate_new_skill()` - LLM call with `skill_generation` prompt → `SkillGenerationOutput` structured output → `Skill`
- `_update_existing_skill()` - LLM call with `skill_update` prompt → merges feedback IDs, bumps version (1.0.0 → 1.1.0)
- `render_skills_markdown(skills)` - Standalone function, exports skills as SKILL.md markdown

**Trigger Decision Tree**:
```
run(request):
  ├─ rerun=True (manual API) → always run, bypass cooldown
  ├─ config.enabled=False → SKIP
  ├─ cooldown not elapsed → SKIP
  └─ Proceed → cluster → filter by min_feedback_per_cluster → generate/update
```

**Auto-Trigger** (in `feedback_generation_service.py`): After aggregation, if `skill_generator_config.enabled` AND `auto_generate_on_aggregation=True`, skill generation runs automatically (non-blocking).

**Configuration** (`SkillGeneratorConfig` in `config_schema.py`, nested in `AgentFeedbackConfig`):
- `enabled: bool = False` - Opt-in
- `min_feedback_per_cluster: int = 5` - Higher threshold than aggregator
- `cooldown_hours: int = 24` - Minimum hours between auto-runs
- `auto_generate_on_aggregation: bool = False` - Auto-trigger after aggregation
- `max_interactions_per_skill: int = 20` - Cap on interactions fetched per cluster

## Prompt IDs

| Constant | Prompt ID | Used By |
|----------|-----------|---------|
| `RAW_FEEDBACK_SHOULD_GENERATE_PROMPT_ID` | `raw_feedback_should_generate` | FeedbackExtractor |
| `RAW_FEEDBACK_EXTRACTION_CONTEXT_PROMPT_ID` | `raw_feedback_extraction_context` | FeedbackExtractor |
| `RAW_FEEDBACK_EXTRACTION_PROMPT_ID` | `raw_feedback_extraction_main` | FeedbackExtractor |
| `FEEDBACK_GENERATION_PROMPT_ID` | `feedback_generation` | FeedbackAggregator |
| `SKILL_GENERATION_PROMPT_ID` | `skill_generation` | SkillGenerator |
| `SKILL_UPDATE_PROMPT_ID` | `skill_update` | SkillGenerator |

## Key Output Schemas (in `feedback_service_utils.py`)

| Class | Purpose |
|-------|---------|
| `StructuredFeedbackContent` | Output from feedback extraction prompt |
| `SkillGenerationOutput` | Output from skill generation/update prompts |
| `FeedbackGenerationRequest` | Request dataclass for feedback extraction |
| `FeedbackAggregatorRequest` | Request dataclass for feedback aggregation |
| `SkillGeneratorRequest` | Request dataclass for skill generation |
