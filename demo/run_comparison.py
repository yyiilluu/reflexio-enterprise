"""
CLI script for running paired conversation comparisons (baseline vs Reflexio-enhanced).

Orchestrates the full pipeline: simulate baseline -> publish to Reflexio -> simulate enhanced -> evaluate.

Usage:
    # Full pipeline
    python demo/run_comparison.py --scenario request_refund \
        --reflexio-api-key KEY --reflexio-url http://localhost:8081

    # Skip publish (Reflexio already has data)
    python demo/run_comparison.py --scenario request_refund \
        --reflexio-api-key KEY --skip-publish

    # Evaluate two existing files only
    python demo/run_comparison.py --evaluate-only demo/output/stable/baseline.jsonl demo/output/stable/enhanced.jsonl
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add demo/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

from evaluate_conversations import compare_conversations, save_evaluation
from reflexio.reflexio_client.reflexio import InteractionData, ReflexioClient, ToolUsed
from reflexio_commons.config_schema import (
    AgentFeedbackConfig,
    FeedbackAggregatorConfig,
    ProfileExtractorConfig,
    StorageConfigLocal,
    StorageConfigSupabase,
)
from scenarios import SCENARIOS
from simulate_conversation import simulate

logger = logging.getLogger(__name__)


def _setup_reflexio_config(client: ReflexioClient) -> None:
    """
    Configure generic profile and feedback extractors on the Reflexio server.

    Sets up a profile extractor and an agent feedback extractor with scenario-agnostic
    prompts so that any demo conversation will produce extracted insights.

    Args:
        client (ReflexioClient): Authenticated Reflexio client
    """
    config = client.get_config()

    # Always set storage — prefer Supabase for vector search, fall back to local
    supabase_url = os.getenv("TEST_SUPABASE_URL")
    supabase_key = os.getenv("TEST_SUPABASE_KEY")
    supabase_db_url = os.getenv("TEST_SUPABASE_DB_URL")
    if supabase_url and supabase_key and supabase_db_url:
        config.storage_config = StorageConfigSupabase(
            url=supabase_url, key=supabase_key, db_url=supabase_db_url
        )
        print(f"  Using Supabase storage at {supabase_url}")
    elif config.storage_config is None:
        demo_storage_dir = str(Path(__file__).resolve().parent / "reflexio_storage")
        config.storage_config = StorageConfigLocal(dir_path=demo_storage_dir)
        print(f"  Using local storage at {demo_storage_dir}")
        print(f"  WARNING: Set TEST_SUPABASE_URL/KEY/DB_URL in .env for semantic search")

    config.profile_extractor_configs = [
        ProfileExtractorConfig(
            extractor_name="demo_profile_extractor",
            profile_content_definition_prompt=(
                "Extract key user information: name, preferences, constraints, "
                "dietary restrictions, account details, technical setup, or any "
                "personal facts mentioned in the conversation."
            ),
            context_prompt="Customer support conversation between a user and an agent.",
            extraction_window_stride_override=1,
            extraction_window_size_override=20,
        )
    ]

    config.agent_feedback_configs = [
        AgentFeedbackConfig(
            feedback_name="demo_feedback",
            feedback_definition_prompt=(
                "Identify cases where the agent made mistakes, missed user needs, "
                "gave incorrect info, or could have handled the situation better. "
                "Focus on actionable corrections the agent should follow in future "
                "interactions."
            ),
            feedback_aggregator_config=FeedbackAggregatorConfig(
                min_feedback_threshold=1
            ),
            extraction_window_stride_override=1,
            extraction_window_size_override=20,
        )
    ]

    resp = client.set_config(config)
    if not resp.get("success"):
        raise RuntimeError(
            f"Failed to set Reflexio config: {resp.get('msg', 'unknown error')}. "
            "Check that the server is running and storage is configured."
        )
    print("Configured extractors:")
    for pc in config.profile_extractor_configs:
        print(f"  Profile: name={pc.extractor_name}, stride={pc.extraction_window_stride_override}, window={pc.extraction_window_size_override}")
    for fc in config.agent_feedback_configs:
        print(f"  Feedback: name={fc.feedback_name}, stride={fc.extraction_window_stride_override}, window={fc.extraction_window_size_override}")


def _publish_to_reflexio(
    filepath: Path,
    client: ReflexioClient,
    user_id: str,
    agent_version: str,
) -> None:
    """
    Publish conversation turns from a JSONL file to Reflexio.

    Args:
        filepath (Path): Path to the JSONL conversation file
        client (ReflexioClient): Authenticated Reflexio client
        user_id (str): User ID for publishing
        agent_version (str): Agent version string
    """
    interactions = []
    with open(filepath) as f:
        for line in f:
            if not line.strip():
                continue
            turn = json.loads(line)
            role = "User" if turn["role"] == "customer" else "Assistant"
            tool_interactions = turn.get("tool_interactions")
            if tool_interactions:
                tools_used = [
                    ToolUsed(
                        tool_name=ti["function_name"],
                        tool_input=ti.get("arguments", {}),
                    )
                    for ti in tool_interactions
                ]
                interactions.append(
                    InteractionData(
                        role=role, content=turn["content"], tools_used=tools_used
                    )
                )
            else:
                interactions.append(InteractionData(role=role, content=turn["content"]))

    resp = client.publish_interaction(
        user_id=user_id,
        interactions=interactions,
        source="demo-comparison",
        agent_version=agent_version,
        wait_for_response=True,
    )
    if resp and resp.success:
        print(f"Published {len(interactions)} interactions to Reflexio (extraction triggered synchronously)")
        if resp.message:
            print(f"  Server message: {resp.message}")
    else:
        msg = resp.message if resp else "no response"
        print(f"WARNING: Publish failed — {msg}")


def _display_reflexio_insights(client: ReflexioClient, user_id: str) -> None:
    """
    Fetch and display all extracted profiles and raw feedbacks from Reflexio.

    Args:
        client (ReflexioClient): Authenticated Reflexio client
        user_id (str): User ID to fetch profiles for
    """
    print("\n" + "=" * 70)
    print("  REFLEXIO EXTRACTED INSIGHTS")
    print("=" * 70)

    # Profiles
    try:
        profile_resp = client.get_profiles(user_id=user_id, force_refresh=True)
        profiles = profile_resp.user_profiles if profile_resp.success else []
        if not profile_resp.success:
            print(f"  WARNING: get_profiles returned success=False — {profile_resp.msg}")
        elif not profiles:
            print(f"  DEBUG: get_profiles success=True but 0 profiles returned (msg={profile_resp.msg})")
    except Exception as e:
        print(f"  FAILED to fetch profiles: {e}")
        profiles = []

    print(f"  User Profiles ({user_id}):")
    print("  " + "-" * 66)
    if profiles:
        for i, p in enumerate(profiles, 1):
            emb_len = len(p.embedding) if p.embedding else 0
            print(f"  {i}. {p.profile_content}")
            print(f"     (embedding: {'yes, dim=' + str(emb_len) if emb_len else 'NONE — search will use substring matching only'})")
    else:
        print("  (none)")

    # Raw feedbacks
    try:
        feedback_resp = client.get_raw_feedbacks()
        feedbacks = feedback_resp.raw_feedbacks if feedback_resp.success else []
        if not feedback_resp.success:
            print(f"  WARNING: get_raw_feedbacks returned success=False — {feedback_resp.msg}")
        elif not feedbacks:
            print(f"  DEBUG: get_raw_feedbacks success=True but 0 feedbacks returned (msg={feedback_resp.msg})")
    except Exception as e:
        print(f"  FAILED to fetch raw feedbacks: {e}")
        feedbacks = []

    print(f"\n  Raw Feedbacks:")
    print("  " + "-" * 66)
    if feedbacks:
        for i, fb in enumerate(feedbacks, 1):
            emb_len = len(fb.embedding) if fb.embedding else 0
            print(f"  {i}. {fb.feedback_name}: {fb.feedback_content}")
            if fb.do_action:
                print(f"     DO:    {fb.do_action}")
            if fb.do_not_action:
                print(f"     DON'T: {fb.do_not_action}")
            if fb.when_condition:
                print(f"     WHEN:  {fb.when_condition}")
            print(f"     (embedding: {'yes, dim=' + str(emb_len) if emb_len else 'NONE — search will use substring matching only'})")
    else:
        print("  (none)")

    print(f"\n  Extraction result: {len(profiles)} profile(s), {len(feedbacks)} feedback(s)")
    if not profiles and not feedbacks:
        print("  WARNING: No insights extracted. Check the server logs for LLM errors")
        print("           (e.g. missing API key, model auth failure, timeout).")
    print("=" * 70)


def _print_summary(result) -> None:
    """Print a formatted summary table of the comparison result."""
    print("\n" + "=" * 70)
    print(f"  COMPARISON RESULT: {result.scenario_name}")
    print("=" * 70)
    print(f"  Baseline: {result.baseline_file}")
    print(f"  Enhanced: {result.enhanced_file}")
    print(f"  Judge:    {result.judge_model}")
    print("-" * 70)

    bm = result.baseline_metrics
    em = result.enhanced_metrics

    print(f"  {'Metric':<30} {'Baseline':>10} {'Enhanced':>10}")
    print(f"  {'-'*30} {'-'*10} {'-'*10}")
    print(f"  {'Resolution':<30} {'Yes' if bm.resolution_success else 'No':>10} {'Yes' if em.resolution_success else 'No':>10}")
    print(f"  {'Total Turns':<30} {bm.total_turns:>10} {em.total_turns:>10}")
    print(f"  {'User Corrections':<30} {bm.user_correction_count:>10} {em.user_correction_count:>10}")
    print(f"  {'Proactivity (1-5)':<30} {bm.agent_proactivity_score:>10} {em.agent_proactivity_score:>10}")
    print(f"  {'Solution Quality (1-5)':<30} {bm.solution_quality_score:>10} {em.solution_quality_score:>10}")
    print(f"  {'Satisfaction (1-5)':<30} {bm.customer_satisfaction_score:>10} {em.customer_satisfaction_score:>10}")
    print(f"  {'Overall (1-10)':<30} {bm.overall_score:>10} {em.overall_score:>10}")
    print("-" * 70)

    winner_display = {
        "baseline": "BASELINE",
        "enhanced": "ENHANCED",
        "tie": "TIE",
    }
    print(f"  Winner: {winner_display.get(result.winner, result.winner)}")
    print(f"  {result.winner_explanation}")
    print()
    print("  Key Differences:")
    for diff in result.key_differences:
        print(f"    - {diff}")
    print("=" * 70)


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run paired conversation comparisons (baseline vs Reflexio-enhanced)."
    )
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()),
        help="Scenario to simulate",
    )
    parser.add_argument(
        "--model",
        default="gpt-5-mini",
        help="Simulation model (default: gpt-5-mini)",
    )
    parser.add_argument(
        "--judge-model",
        default="gpt-5-mini",
        help="Evaluation judge model (default: gpt-5-mini)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=30,
        help="Max conversation turns (default: 30)",
    )
    parser.add_argument(
        "--reflexio-api-key",
        help="Reflexio API key",
    )
    parser.add_argument(
        "--reflexio-url",
        default="http://localhost:8081",
        help="Reflexio server URL (default: http://localhost:8081)",
    )
    parser.add_argument(
        "--reflexio-user-id",
        default="demo-user",
        help="Reflexio user ID (default: demo-user)",
    )
    parser.add_argument(
        "--reflexio-agent-version",
        default="demo-v1",
        help="Reflexio agent version (default: demo-v1)",
    )
    parser.add_argument(
        "--skip-publish",
        action="store_true",
        help="Skip publishing baseline to Reflexio (use when data already exists)",
    )
    parser.add_argument(
        "--evaluate-only",
        nargs=2,
        metavar=("BASELINE", "ENHANCED"),
        help="Skip simulation, just evaluate two existing JSONL files",
    )
    return parser.parse_args()


def _run_evaluate_only(args: argparse.Namespace) -> None:
    """
    Evaluate two existing JSONL conversation files without running simulations.

    Args:
        args (argparse.Namespace): Parsed CLI arguments with evaluate_only and judge_model
    """
    baseline_path = Path(args.evaluate_only[0])
    enhanced_path = Path(args.evaluate_only[1])

    if not baseline_path.exists():
        print(f"Error: baseline file not found: {baseline_path}")
        sys.exit(1)
    if not enhanced_path.exists():
        print(f"Error: enhanced file not found: {enhanced_path}")
        sys.exit(1)

    print(f"Evaluating: {baseline_path.name} vs {enhanced_path.name}")
    result = compare_conversations(baseline_path, enhanced_path, args.judge_model)
    eval_path = save_evaluation(result)
    print(f"Saved evaluation to: {eval_path}")
    _print_summary(result)


def _run_full_pipeline(args: argparse.Namespace) -> None:
    """
    Run the full comparison pipeline: baseline simulation, Reflexio publish,
    enhanced simulation, and evaluation.

    Args:
        args (argparse.Namespace): Parsed CLI arguments
    """
    if not args.scenario:
        print("Error: --scenario is required unless using --evaluate-only")
        sys.exit(1)

    if not args.reflexio_api_key:
        print("Error: --reflexio-api-key is required for full pipeline")
        sys.exit(1)

    # Step 1: Baseline simulation
    print(f"\n[1/4] Running baseline simulation ({args.scenario})...")
    baseline_path = simulate(
        args.scenario, args.model, args.max_turns, output_path=None
    )
    print(f"  -> {baseline_path}")

    # Step 2: Publish to Reflexio
    client = ReflexioClient(
        api_key=args.reflexio_api_key, url_endpoint=args.reflexio_url
    )
    _setup_reflexio_config(client)

    if not args.skip_publish:
        print("\n[2/4] Publishing baseline to Reflexio...")
        _publish_to_reflexio(
            baseline_path, client, args.reflexio_user_id, args.reflexio_agent_version
        )
    else:
        print("\n[2/4] Skipping publish (--skip-publish)")

    _display_reflexio_insights(client, args.reflexio_user_id)

    # Step 3: Enhanced simulation (with Reflexio)
    print(f"\n[3/4] Running enhanced simulation ({args.scenario} + Reflexio)...")
    reflexio_config = {
        "client": client,
        "user_id": args.reflexio_user_id,
        "agent_version": args.reflexio_agent_version,
    }
    enhanced_path = simulate(
        args.scenario,
        args.model,
        args.max_turns,
        output_path=None,
        reflexio_config=reflexio_config,
    )
    print(f"  -> {enhanced_path}")

    # Step 4: Evaluate
    print(f"\n[4/4] Evaluating conversations (judge: {args.judge_model})...")
    result = compare_conversations(baseline_path, enhanced_path, args.judge_model)
    eval_path = save_evaluation(result)
    print(f"  Saved evaluation to: {eval_path}")

    _print_summary(result)


def main():
    args = _parse_args()

    if args.evaluate_only:
        _run_evaluate_only(args)
    else:
        _run_full_pipeline(args)


if __name__ == "__main__":
    main()
