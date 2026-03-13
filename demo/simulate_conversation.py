"""
Simulate a multi-turn customer support conversation between two independent AI agents.

Each agent (customer and support) has its own system prompt and message history.
The output is a JSONL file matching the format used in evaluation data.

Usage:
    python demo/simulate_conversation.py
    python demo/simulate_conversation.py --model gpt-4o --max-turns 20
    python demo/simulate_conversation.py --scenario devops_backup_failure --output my_output.jsonl
"""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

import litellm
from dotenv import load_dotenv
from scenarios import DEFAULT_SCENARIO, SCENARIOS

logger = logging.getLogger(__name__)

# Load env from project root .env
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

RESOLUTION_PHRASES = [
    "resolves everything",
    "that's all",
    "that resolves everything",
]

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def get_reflexio_context(reflexio_config: dict, query: str) -> str:
    """
    Fetch user profiles and agent feedback from Reflexio and format them as a context block
    to inject into the agent's system prompt.

    Args:
        reflexio_config (dict): Must contain 'client' (ReflexioClient), 'user_id' (str),
            and 'agent_version' (str)
        query (str): The latest customer message to use as a search query

    Returns:
        str: Formatted markdown context block, or empty string on failure
    """
    try:
        client = reflexio_config["client"]
        user_id = reflexio_config["user_id"]
        agent_version = reflexio_config["agent_version"]

        print(f'  [Reflexio] Searching with query: "{query[:80]}"')

        profile_section = ""
        profiles_found = []
        try:
            profile_resp = client.search_profiles(
                user_id=user_id, query=query, top_k=10, threshold=0.1
            )
            if profile_resp.success and profile_resp.user_profiles:
                profiles_found = profile_resp.user_profiles
                lines = [f"- {p.profile_content}" for p in profile_resp.user_profiles]
                profile_section = (
                    "\n## Known User Preferences & Information\n" + "\n".join(lines)
                )
            else:
                print(
                    f"    Profiles: 0 results (success={profile_resp.success}, msg={profile_resp.msg})"
                )
        except Exception as e:
            print(f"    Profiles: FAILED — {e}")

        feedback_section = ""
        feedbacks_found = []
        try:
            feedback_resp = client.search_raw_feedbacks(
                query=query, agent_version=agent_version, top_k=5, threshold=0.1
            )
            if feedback_resp.success and feedback_resp.raw_feedbacks:
                feedbacks_found = feedback_resp.raw_feedbacks
                lines = []
                for fb in feedback_resp.raw_feedbacks:
                    parts = [f"- {fb.feedback_content}"]
                    if fb.do_action:
                        parts.append(f"  DO: {fb.do_action}")
                    if fb.do_not_action:
                        parts.append(f"  DON'T: {fb.do_not_action}")
                    if fb.when_condition:
                        parts.append(f"  WHEN: {fb.when_condition}")
                    lines.append("\n".join(parts))
                feedback_section = (
                    "\n## Behavior Corrections\n"
                    "The following rules are learned from past mistakes and OVERRIDE your standard flow above. "
                    "Before responding, check each rule: if the WHEN condition matches the current situation, "
                    "you MUST follow the DO/DON'T actions even if they differ from your default steps.\n\n"
                    + "\n\n".join(lines)
                )
            else:
                print(
                    f"    Feedbacks: 0 results (success={feedback_resp.success}, msg={feedback_resp.msg})"
                )
        except Exception as e:
            print(f"    Feedbacks: FAILED — {e}")

        if not profile_section and not feedback_section:
            print(
                "    -> No context injected (local storage uses substring matching, not semantic search)"
            )
            return ""

        # Display retrieved context for this turn
        print(
            f"    -> Matched {len(profiles_found)} profile(s), {len(feedbacks_found)} feedback(s)"
        )
        if profiles_found:
            print("    Profiles:")
            for p in profiles_found:
                emb_status = (
                    f"embedding[{len(p.embedding)}]" if p.embedding else "no-embedding"
                )
                snippet = p.profile_content[:120] + (
                    "..." if len(p.profile_content) > 120 else ""
                )
                print(f"      - [{emb_status}] {snippet}")
        if feedbacks_found:
            print("    Feedbacks:")
            for fb in feedbacks_found:
                emb_status = (
                    f"embedding[{len(fb.embedding)}]"
                    if fb.embedding
                    else "no-embedding"
                )
                snippet = fb.feedback_content[:120] + (
                    "..." if len(fb.feedback_content) > 120 else ""
                )
                print(f"      - [{emb_status}] {snippet}")

        return (
            "\n\n---\n# Context and Corrections"
            + profile_section
            + feedback_section
            + "\n---"
        )
    except Exception as e:
        logger.warning(f"Failed to get Reflexio context: {e}")
        return ""


def get_mem0_context(mem0_config: dict, query: str) -> str:
    """
    Fetch relevant memories from mem0 and format them as a context block
    to inject into the agent's system prompt.

    Args:
        mem0_config (dict): Must contain 'api_key' (str) and 'user_id' (str)
        query (str): The latest customer message to use as a search query

    Returns:
        str: Formatted markdown context block, or empty string on failure
    """
    try:
        from mem0 import MemoryClient

        client = MemoryClient(api_key=mem0_config["api_key"])
        results = client.search(
            query,
            user_id=mem0_config["user_id"],
            top_k=5,
        )

        if not results:
            return ""

        lines = []
        for result in results:
            memory = result.get("memory", "")
            if memory:
                lines.append(f"- {memory}")

        if not lines:
            return ""

        return (
            "\n\n---\n# CONTEXT (from mem0 memories)"
            "\n## Remembered User Information\n" + "\n".join(lines) + "\n---"
        )
    except Exception as e:
        logger.warning(f"Failed to get mem0 context: {e}")
        return ""


_BEHAVIOR_REMINDER = (
    "**Note: You have information about the user from context and behavior corrections from past interactions in this "
    "prompt. Before responding to user, make use of known user information and follow corrections in current situation if applicable.**\n\n"
)


def build_enhanced_prompt(base_system_prompt: str, context: str) -> str:
    """
    Build the enhanced system prompt by prepending a behavior reminder at the top,
    followed by the context block, then the base system prompt.

    Args:
        base_system_prompt (str): The original agent system prompt
        context (str): The reflexio context block (profiles + feedback)

    Returns:
        str: The enhanced prompt with reminder at top and context at bottom
    """
    return _BEHAVIOR_REMINDER + context + "\n\n" + base_system_prompt


def check_resolution(content: str) -> bool:
    """
    Check if the customer's message contains a resolution phrase signaling the conversation is done.

    Args:
        content (str): The customer's message text

    Returns:
        bool: True if a resolution phrase is detected
    """
    lower = content.lower()
    return any(phrase in lower for phrase in RESOLUTION_PHRASES)


def get_completion(model: str, messages: list[dict], tools: list | None = None) -> dict:
    """
    Call the LLM and return the assistant's response, handling any tool calls in a loop.

    When tools are provided, the LLM may request tool calls instead of returning text.
    This function executes the mock tool handlers and feeds results back to the LLM
    until it produces a final text response.

    Args:
        model (str): The model identifier (e.g. 'gpt-4o-mini')
        messages (list[dict]): The conversation messages in OpenAI format
        tools (list | None): Optional list of ScenarioTool objects for function calling

    Returns:
        dict: {"content": str, "tool_interactions": list | None}
              tool_interactions is a list of dicts with tool_call_id, function_name,
              arguments, and result — or None if no tools were called.
    """
    if not tools:
        response = litellm.completion(model=model, messages=messages)
        return {
            "content": response.choices[0].message.content.strip(),
            "tool_interactions": None,
        }

    openai_tools = [t.to_openai_tool() for t in tools]
    handler_map = {t.name: t.handler for t in tools}

    # Work on a copy so intermediate tool messages don't leak to the caller
    local_messages = list(messages)
    collected_interactions = []

    max_rounds = 10
    for _ in range(max_rounds):
        response = litellm.completion(
            model=model, messages=local_messages, tools=openai_tools, tool_choice="auto"
        )
        choice = response.choices[0]

        if not choice.message.tool_calls:
            content = (choice.message.content or "").strip()
            return {
                "content": content,
                "tool_interactions": collected_interactions or None,
            }

        # Append the assistant message (with tool_calls) to local history
        local_messages.append(choice.message.model_dump())

        for tool_call in choice.message.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            handler = handler_map.get(fn_name)
            if handler:
                result = handler(fn_args)
            else:
                result = {"error": f"Unknown tool: {fn_name}"}

            collected_interactions.append(
                {
                    "tool_call_id": tool_call.id,
                    "function_name": fn_name,
                    "arguments": fn_args,
                    "result": result,
                }
            )

            local_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                }
            )

    # Fallback: if we exhausted rounds, return whatever we have
    last_content = ""
    for msg in reversed(local_messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            last_content = msg["content"]
            break
    return {
        "content": last_content.strip(),
        "tool_interactions": collected_interactions or None,
    }


def simulate(
    scenario_name: str,
    model: str,
    max_turns: int,
    output_path: Path | None,
    reflexio_config: dict | None = None,
    mem0_config: dict | None = None,
) -> Path:
    """
    Run a full conversation simulation between customer and agent.

    Args:
        scenario_name (str): Key into the SCENARIOS dict
        model (str): LLM model to use for both agents
        max_turns (int): Maximum number of turns before stopping
        output_path (Path | None): Where to write the JSONL file. Auto-generated if None.
        reflexio_config (dict | None): Optional Reflexio config with 'client', 'user_id', 'agent_version'
        mem0_config (dict | None): Optional mem0 config with 'api_key' and 'user_id'

    Returns:
        Path: The path to the written JSONL file
    """
    scenario = SCENARIOS[scenario_name]
    base_system_prompt = scenario.agent_system_prompt

    # Each agent maintains its own message history
    customer_messages = [{"role": "system", "content": scenario.customer_system_prompt}]
    agent_messages = [{"role": "system", "content": base_system_prompt}]

    turns: list[dict] = []
    turn_num = 0

    # --- Turn 1: Customer opening message ---
    turn_num += 1
    customer_text = scenario.customer_opening_message
    turns.append(
        {"turn": turn_num, "role": "customer", "content": customer_text, "labels": []}
    )
    print(f"[Turn {turn_num}] Customer: {customer_text}")

    # Add to histories: customer said this (assistant in customer's history, user in agent's history)
    customer_messages.append({"role": "assistant", "content": customer_text})
    agent_messages.append({"role": "user", "content": customer_text})

    while turn_num < max_turns:
        # --- Agent responds (with optional Reflexio context injection) ---
        turn_num += 1
        turn_system_prompt = None

        if reflexio_config:
            # Get latest customer message as query
            latest_customer_msg = customer_text
            context = get_reflexio_context(reflexio_config, latest_customer_msg)
            if context:
                enhanced_prompt = build_enhanced_prompt(base_system_prompt, context)
                agent_messages[0]["content"] = enhanced_prompt
                turn_system_prompt = enhanced_prompt
        elif mem0_config:
            latest_customer_msg = customer_text
            context = get_mem0_context(mem0_config, latest_customer_msg)
            if context:
                enhanced_prompt = build_enhanced_prompt(base_system_prompt, context)
                agent_messages[0]["content"] = enhanced_prompt
                turn_system_prompt = enhanced_prompt

        result = get_completion(model, agent_messages, tools=scenario.tools or None)
        agent_text = result["content"]
        tool_interactions = result["tool_interactions"]

        # Restore original system prompt
        if reflexio_config or mem0_config:
            agent_messages[0]["content"] = base_system_prompt

        turn_dict = {
            "turn": turn_num,
            "role": "agent",
            "content": agent_text,
            "labels": [],
        }
        if tool_interactions:
            turn_dict["tool_interactions"] = tool_interactions
        if turn_system_prompt:
            turn_dict["system_prompt"] = turn_system_prompt
            turn_dict["context_source"] = "reflexio" if reflexio_config else "mem0"
        turns.append(turn_dict)
        print(f"[Turn {turn_num}] Agent ({model}): {agent_text}")
        if tool_interactions:
            for ti in tool_interactions:
                print(
                    f"  [Tool] {ti['function_name']}({ti['arguments']}) -> {ti['result']}"
                )

        # Add to histories
        agent_messages.append({"role": "assistant", "content": agent_text})
        customer_messages.append({"role": "user", "content": agent_text})

        if turn_num >= max_turns:
            print(f"\n--- Max turns ({max_turns}) reached ---")
            break

        # --- Customer responds ---
        turn_num += 1
        result = get_completion(model, customer_messages)
        customer_text = result["content"]
        turns.append(
            {
                "turn": turn_num,
                "role": "customer",
                "content": customer_text,
                "labels": [],
            }
        )
        print(f"[Turn {turn_num}] Customer ({model}): {customer_text}")

        # Add to histories
        customer_messages.append({"role": "assistant", "content": customer_text})
        agent_messages.append({"role": "user", "content": customer_text})

        # Check for resolution
        if check_resolution(customer_text):
            print("\n--- Conversation resolved naturally ---")
            break

        if turn_num >= max_turns:
            print(f"\n--- Max turns ({max_turns}) reached ---")

    # Write output
    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if reflexio_config:
            suffix = "_reflexio"
        elif mem0_config:
            suffix = "_mem0"
        else:
            suffix = ""
        output_path = OUTPUT_DIR / f"{scenario_name}{suffix}_{timestamp}.jsonl"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.writelines(json.dumps(turn) + "\n" for turn in turns)

    print(f"\nWrote {len(turns)} turns to {output_path}")
    return output_path


def simulate_stream(
    scenario_name: str,
    model: str,
    max_turns: int,
    reflexio_config: dict | None = None,
    mem0_config: dict | None = None,
):
    """
    Generator version of simulate() that yields each turn as it's produced for real-time streaming.

    Yields dicts with an "event" key:
    - {"event": "scenario", ...} — scenario metadata (first yield)
    - {"event": "turn", ...} — each conversation turn as it's generated
    - {"event": "done", "filename": ...} — final event with the output filename

    Also writes each turn incrementally to a JSONL file.

    Args:
        scenario_name (str): Key into the SCENARIOS dict
        model (str): LLM model to use for both agents
        max_turns (int): Maximum number of turns before stopping
        reflexio_config (dict | None): Optional Reflexio config with 'client', 'user_id', 'agent_version'
        mem0_config (dict | None): Optional mem0 config with 'api_key' and 'user_id'
    """
    scenario = SCENARIOS[scenario_name]
    base_system_prompt = scenario.agent_system_prompt

    # Yield scenario metadata first
    yield {
        "event": "scenario",
        "key": scenario_name,
        "name": scenario.name,
        "description": scenario.description,
        "agent_system_prompt": scenario.agent_system_prompt,
        "customer_system_prompt": scenario.customer_system_prompt,
        "customer_opening_message": scenario.customer_opening_message,
        "max_turns": scenario.max_turns,
    }

    # Prepare output file
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if reflexio_config:
        suffix = "_reflexio"
    elif mem0_config:
        suffix = "_mem0"
    else:
        suffix = ""
    output_path = OUTPUT_DIR / f"{scenario_name}{suffix}_{timestamp}.jsonl"

    # Each agent maintains its own message history
    customer_messages = [{"role": "system", "content": scenario.customer_system_prompt}]
    agent_messages = [{"role": "system", "content": base_system_prompt}]

    turn_num = 0

    # --- Turn 1: Customer opening message ---
    turn_num += 1
    customer_text = scenario.customer_opening_message
    turn_dict = {
        "turn": turn_num,
        "role": "customer",
        "content": customer_text,
        "labels": [],
    }

    with open(output_path, "a") as f:
        f.write(json.dumps(turn_dict) + "\n")

    yield {"event": "turn", **turn_dict}
    print(f"[Turn {turn_num}] Customer: {customer_text}")

    customer_messages.append({"role": "assistant", "content": customer_text})
    agent_messages.append({"role": "user", "content": customer_text})

    while turn_num < max_turns:
        # --- Agent responds (with optional Reflexio context injection) ---
        turn_num += 1
        turn_system_prompt = None

        if reflexio_config:
            latest_customer_msg = customer_text
            context = get_reflexio_context(reflexio_config, latest_customer_msg)
            if context:
                enhanced_prompt = build_enhanced_prompt(base_system_prompt, context)
                agent_messages[0]["content"] = enhanced_prompt
                turn_system_prompt = enhanced_prompt
        elif mem0_config:
            latest_customer_msg = customer_text
            context = get_mem0_context(mem0_config, latest_customer_msg)
            if context:
                enhanced_prompt = build_enhanced_prompt(base_system_prompt, context)
                agent_messages[0]["content"] = enhanced_prompt
                turn_system_prompt = enhanced_prompt

        result = get_completion(model, agent_messages, tools=scenario.tools or None)
        agent_text = result["content"]
        tool_interactions = result["tool_interactions"]

        # Restore original system prompt
        if reflexio_config or mem0_config:
            agent_messages[0]["content"] = base_system_prompt

        turn_dict = {
            "turn": turn_num,
            "role": "agent",
            "content": agent_text,
            "labels": [],
        }
        if tool_interactions:
            turn_dict["tool_interactions"] = tool_interactions
        if turn_system_prompt:
            turn_dict["system_prompt"] = turn_system_prompt
            turn_dict["context_source"] = "reflexio" if reflexio_config else "mem0"

        with open(output_path, "a") as f:
            f.write(json.dumps(turn_dict) + "\n")

        yield {"event": "turn", **turn_dict}
        print(f"[Turn {turn_num}] Agent ({model}): {agent_text}")
        if tool_interactions:
            for ti in tool_interactions:
                print(
                    f"  [Tool] {ti['function_name']}({ti['arguments']}) -> {ti['result']}"
                )

        agent_messages.append({"role": "assistant", "content": agent_text})
        customer_messages.append({"role": "user", "content": agent_text})

        if turn_num >= max_turns:
            print(f"\n--- Max turns ({max_turns}) reached ---")
            break

        # --- Customer responds ---
        turn_num += 1
        result = get_completion(model, customer_messages)
        customer_text = result["content"]
        turn_dict = {
            "turn": turn_num,
            "role": "customer",
            "content": customer_text,
            "labels": [],
        }

        with open(output_path, "a") as f:
            f.write(json.dumps(turn_dict) + "\n")

        yield {"event": "turn", **turn_dict}
        print(f"[Turn {turn_num}] Customer ({model}): {customer_text}")

        customer_messages.append({"role": "assistant", "content": customer_text})
        agent_messages.append({"role": "user", "content": customer_text})

        if check_resolution(customer_text):
            print("\n--- Conversation resolved naturally ---")
            break

        if turn_num >= max_turns:
            print(f"\n--- Max turns ({max_turns}) reached ---")

    print(f"\nWrote turns to {output_path}")
    yield {"event": "done", "filename": output_path.name}


def main():
    parser = argparse.ArgumentParser(
        description="Simulate a customer support conversation between two AI agents."
    )
    parser.add_argument(
        "--scenario",
        default=DEFAULT_SCENARIO,
        choices=list(SCENARIOS.keys()),
        help=f"Scenario to simulate (default: {DEFAULT_SCENARIO})",
    )
    parser.add_argument(
        "--model",
        default="minimax/MiniMax-M2.5",
        help="LLM model to use (default: minimax/MiniMax-M2.5)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=20,
        help="Maximum number of conversation turns (default: 20)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSONL file path (default: demo/output/<scenario>_<timestamp>.jsonl)",
    )
    args = parser.parse_args()
    simulate(args.scenario, args.model, args.max_turns, args.output)


if __name__ == "__main__":
    main()
