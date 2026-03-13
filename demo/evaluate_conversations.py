"""
LLM-as-judge evaluation engine for comparing conversation pairs.

Evaluates individual conversations and compares baseline vs enhanced (Reflexio) runs
using structured LLM output.

Usage:
    from evaluate_conversations import compare_conversations, evaluate_single
    result = compare_conversations("baseline.jsonl", "enhanced.jsonl", "gpt-5-mini")
"""

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path

import litellm
from dotenv import load_dotenv
from pydantic import BaseModel

from scenarios import SCENARIOS

logger = logging.getLogger(__name__)

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
EVALUATIONS_DIR = OUTPUT_DIR / "evaluations"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ConversationMetrics(BaseModel):
    """Metrics from evaluating a single conversation."""

    resolution_success: bool
    resolution_explanation: str
    total_turns: int
    user_correction_count: int
    user_corrections: list[str]
    agent_proactivity_score: int  # 1-5
    solution_quality_score: int  # 1-5
    customer_satisfaction_score: int  # 1-5
    overall_score: int  # 1-10
    overall_explanation: str


class ComparisonResult(BaseModel):
    """Result of comparing two conversations from the same scenario."""

    scenario_name: str
    scenario_description: str
    baseline_file: str
    enhanced_file: str
    baseline_metrics: ConversationMetrics
    enhanced_metrics: ConversationMetrics
    winner: str  # "baseline" | "enhanced" | "tie"
    winner_explanation: str
    key_differences: list[str]
    evaluated_at: str
    judge_model: str


# ---------------------------------------------------------------------------
# Transcript formatting
# ---------------------------------------------------------------------------


def format_transcript(turns: list[dict]) -> str:
    """
    Format JSONL turns into a readable dialogue transcript for the LLM judge.

    Args:
        turns (list[dict]): List of turn dicts from a JSONL conversation file

    Returns:
        str: Formatted conversation transcript
    """
    lines = []
    for turn in turns:
        role = "Customer" if turn["role"] == "customer" else "Agent"
        content = turn.get("content", "")

        tool_interactions = turn.get("tool_interactions")
        if tool_interactions:
            tool_parts = []
            for ti in tool_interactions:
                tool_parts.append(
                    f"[Tool: {ti['function_name']}({json.dumps(ti.get('arguments', {}))}) "
                    f"-> {json.dumps(ti.get('result', {}))}]"
                )
            tool_str = " ".join(tool_parts)
            lines.append(f"Turn {turn['turn']} - {role}: {tool_str} {content}")
        else:
            lines.append(f"Turn {turn['turn']} - {role}: {content}")

    return "\n".join(lines)


def _load_turns(filepath: Path) -> list[dict]:
    """Load turns from a JSONL file."""
    turns = []
    with open(filepath) as f:
        for line in f:
            if line.strip():
                turns.append(json.loads(line))
    return turns


def match_scenario(filename: str) -> str | None:
    """
    Match a JSONL filename to a scenario key.

    Args:
        filename (str): The JSONL filename

    Returns:
        str | None: Scenario key if matched, None otherwise
    """
    for key in SCENARIOS:
        if filename.startswith(key):
            return key
    return None


# ---------------------------------------------------------------------------
# Single conversation evaluation
# ---------------------------------------------------------------------------

SINGLE_EVAL_SYSTEM_PROMPT = """\
You are an expert evaluator of customer support conversations. You analyze conversations
between a customer and an AI support agent to assess agent performance.

Evaluate the conversation against the provided criteria and return a JSON object with these fields:
- resolution_success (bool): Whether the customer's issue was fully resolved
- resolution_explanation (string): Why or why not
- total_turns (int): Total number of turns in the conversation
- user_correction_count (int): Number of times the customer had to redirect or correct the agent
- user_corrections (list of strings): Brief description of each correction
- agent_proactivity_score (int 1-5): Did the agent anticipate needs and act proactively?
- solution_quality_score (int 1-5): How good was the final solution?
- customer_satisfaction_score (int 1-5): Inferred from customer's tone and reactions
- overall_score (int 1-10): Overall rating
- overall_explanation (string): Explanation of the overall score

Return ONLY valid JSON, no other text."""


def evaluate_single(
    turns: list[dict],
    scenario_key: str,
    model: str = "gpt-5-mini",
) -> ConversationMetrics:
    """
    Evaluate a single conversation using an LLM judge.

    Args:
        turns (list[dict]): Conversation turns
        scenario_key (str): Key into SCENARIOS dict
        model (str): LLM model to use as judge

    Returns:
        ConversationMetrics: Structured evaluation metrics
    """
    scenario = SCENARIOS[scenario_key]
    transcript = format_transcript(turns)

    user_prompt = f"""## Scenario
**Name**: {scenario.name}
**Description**: {scenario.description}

## Evaluation Criteria
{scenario.evaluation_criteria}

## Agent System Prompt
{scenario.agent_system_prompt}

## Conversation Transcript
{transcript}

Evaluate this conversation and return the metrics as JSON."""

    messages = [
        {"role": "system", "content": SINGLE_EVAL_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    response = litellm.completion(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
    )

    result_text = response.choices[0].message.content.strip()
    result_data = json.loads(result_text)
    return ConversationMetrics(**result_data)


# ---------------------------------------------------------------------------
# Pairwise comparison
# ---------------------------------------------------------------------------

PAIRWISE_SYSTEM_PROMPT = """\
You are comparing two customer support conversations for the same scenario.
Determine which agent performed better overall.

Return a JSON object with:
- winner (string): "A" or "B" or "tie"
- winner_explanation (string): Why this conversation was better
- key_differences (list of strings): 3-5 specific differences between the conversations

Return ONLY valid JSON, no other text."""


def _run_pairwise(
    turns_a: list[dict],
    turns_b: list[dict],
    scenario_key: str,
    model: str,
) -> dict:
    """
    Run a pairwise comparison between two conversations.

    Args:
        turns_a (list[dict]): First conversation turns
        turns_b (list[dict]): Second conversation turns
        scenario_key (str): Key into SCENARIOS dict
        model (str): LLM model to use as judge

    Returns:
        dict: Raw comparison result with winner, winner_explanation, key_differences
    """
    scenario = SCENARIOS[scenario_key]
    transcript_a = format_transcript(turns_a)
    transcript_b = format_transcript(turns_b)

    user_prompt = f"""## Scenario
**Name**: {scenario.name}
**Description**: {scenario.description}

## Evaluation Criteria
{scenario.evaluation_criteria}

## Conversation A
{transcript_a}

## Conversation B
{transcript_b}

Compare these two conversations and determine which agent performed better."""

    messages = [
        {"role": "system", "content": PAIRWISE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    response = litellm.completion(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content.strip())


def compare_conversations(
    baseline_path: str | Path,
    enhanced_path: str | Path,
    judge_model: str = "gpt-5-mini",
) -> ComparisonResult:
    """
    Evaluate and compare two conversations from the same scenario.

    Uses position bias mitigation by randomly assigning baseline/enhanced to A/B positions,
    then mapping the result back.

    Args:
        baseline_path (str | Path): Path to baseline JSONL file
        enhanced_path (str | Path): Path to enhanced JSONL file
        judge_model (str): LLM model to use as judge

    Returns:
        ComparisonResult: Full comparison result with metrics and winner
    """
    baseline_path = Path(baseline_path)
    enhanced_path = Path(enhanced_path)

    # Match scenario from filename
    scenario_key = match_scenario(baseline_path.name)
    if not scenario_key:
        scenario_key = match_scenario(enhanced_path.name)
    if not scenario_key:
        raise ValueError(
            f"Could not match scenario from filenames: {baseline_path.name}, {enhanced_path.name}"
        )

    scenario = SCENARIOS[scenario_key]

    # Load turns
    baseline_turns = _load_turns(baseline_path)
    enhanced_turns = _load_turns(enhanced_path)

    # Evaluate each individually
    logger.info("Evaluating baseline conversation...")
    baseline_metrics = evaluate_single(baseline_turns, scenario_key, judge_model)

    logger.info("Evaluating enhanced conversation...")
    enhanced_metrics = evaluate_single(enhanced_turns, scenario_key, judge_model)

    # Pairwise comparison with randomized position to mitigate position bias
    baseline_is_a = random.choice([True, False])

    if baseline_is_a:
        turns_a, turns_b = baseline_turns, enhanced_turns
    else:
        turns_a, turns_b = enhanced_turns, baseline_turns

    logger.info(
        f"Running pairwise comparison (baseline={'A' if baseline_is_a else 'B'})..."
    )
    pairwise = _run_pairwise(turns_a, turns_b, scenario_key, judge_model)

    # Map A/B winner back to baseline/enhanced
    raw_winner = pairwise.get("winner", "tie").upper()
    if raw_winner == "A":
        winner = "baseline" if baseline_is_a else "enhanced"
    elif raw_winner == "B":
        winner = "enhanced" if baseline_is_a else "baseline"
    else:
        winner = "tie"

    return ComparisonResult(
        scenario_name=scenario.name,
        scenario_description=scenario.description,
        baseline_file=baseline_path.name,
        enhanced_file=enhanced_path.name,
        baseline_metrics=baseline_metrics,
        enhanced_metrics=enhanced_metrics,
        winner=winner,
        winner_explanation=pairwise.get("winner_explanation", ""),
        key_differences=pairwise.get("key_differences", []),
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        judge_model=judge_model,
    )


# ---------------------------------------------------------------------------
# Save / Load
# ---------------------------------------------------------------------------


def save_evaluation(result: ComparisonResult) -> Path:
    """
    Save a ComparisonResult to the evaluations directory.

    Args:
        result (ComparisonResult): The evaluation result to save

    Returns:
        Path: Path to the saved JSON file
    """
    EVALUATIONS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{result.scenario_name}_{timestamp}_eval.json"
    filepath = EVALUATIONS_DIR / filename
    filepath.write_text(result.model_dump_json(indent=2))
    return filepath


def load_evaluation(filepath: str | Path) -> ComparisonResult:
    """
    Load a ComparisonResult from a JSON file.

    Args:
        filepath (str | Path): Path to the evaluation JSON file

    Returns:
        ComparisonResult: The loaded evaluation result
    """
    filepath = Path(filepath)
    return ComparisonResult.model_validate_json(filepath.read_text())
