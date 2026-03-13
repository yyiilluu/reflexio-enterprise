"""
FastAPI server for the Conversation Viewer demo UI.

Serves the viewer HTML and provides API endpoints for listing, viewing,
simulating, and deleting conversation JSONL files.

Usage:
    python demo/serve_viewer.py
    # Open http://localhost:8083
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

# Load demo/.env for MEM0_API_KEY etc.
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

# Add demo/ to path so we can import sibling modules
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate_conversations import (
    ComparisonResult,
    compare_conversations,
    evaluate_single,
    load_evaluation,
    match_scenario as eval_match_scenario,
    save_evaluation,
    EVALUATIONS_DIR,
)
from reflexio.reflexio_client.reflexio import InteractionData, ReflexioClient, ToolUsed
from scenarios import SCENARIOS
from simulate_conversation import (
    build_enhanced_prompt,
    get_completion,
    get_mem0_context,
    get_reflexio_context,
    simulate,
    simulate_stream,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Conversation Viewer")

DEMO_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = (DEMO_DIR / "output").resolve()
VIEWER_HTML = DEMO_DIR / "viewer.html"

# Module-level Reflexio client state
reflexio_client: Optional[ReflexioClient] = None


def match_scenario(filename: str) -> dict | None:
    """
    Match a JSONL filename to a scenario by checking if the filename starts with a scenario key.

    Args:
        filename (str): The JSONL filename (e.g. 'devops_backup_failure_20260131_234439.jsonl')

    Returns:
        dict | None: Scenario data dict if matched, None otherwise
    """
    for key, scenario in SCENARIOS.items():
        if filename.startswith(key):
            return {
                "key": key,
                "name": scenario.name,
                "description": scenario.description,
                "agent_system_prompt": scenario.agent_system_prompt,
                "customer_system_prompt": scenario.customer_system_prompt,
                "customer_opening_message": scenario.customer_opening_message,
                "max_turns": scenario.max_turns,
            }
    return None


@app.get("/")
async def serve_viewer():
    """Serve the viewer HTML page."""
    return FileResponse(VIEWER_HTML, media_type="text/html")


@app.get("/api/scenarios")
async def list_scenarios():
    """Return available simulation scenarios."""
    return JSONResponse(
        [
            {"key": key, "name": scenario.name, "description": scenario.description}
            for key, scenario in SCENARIOS.items()
        ]
    )


@app.get("/api/scenario/{key}")
async def get_scenario(key: str):
    """Return full scenario data for a single scenario by key."""
    if key not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {key}")
    scenario = SCENARIOS[key]
    return JSONResponse(
        {
            "key": key,
            "name": scenario.name,
            "description": scenario.description,
            "agent_system_prompt": scenario.agent_system_prompt,
            "customer_system_prompt": scenario.customer_system_prompt,
            "customer_opening_message": scenario.customer_opening_message,
            "max_turns": scenario.max_turns,
        }
    )


@app.get("/api/conversations")
async def list_conversations():
    """
    List all conversation JSONL files in the output directory.
    Returns filename, scenario name, description, timestamp, and turn count.
    Sorted most-recent first.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conversations = []

    for filepath in OUTPUT_DIR.rglob("*.jsonl"):
        turn_count = 0
        with open(filepath) as f:
            for line in f:
                if line.strip():
                    turn_count += 1

        # Use relative path from OUTPUT_DIR so subdirs are preserved
        rel_path = filepath.relative_to(OUTPUT_DIR)
        scenario = match_scenario(filepath.name)
        # Extract timestamp from filename: scenario_YYYYMMDD_HHMMSS.jsonl
        timestamp = None
        stem = filepath.stem
        parts = stem.rsplit("_", 2)
        if len(parts) >= 3:
            try:
                ts_str = f"{parts[-2]}_{parts[-1]}"
                dt = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                timestamp = dt.isoformat()
            except ValueError:
                pass

        # Directory relative to output root (empty string for top-level files)
        directory = str(rel_path.parent) if rel_path.parent != Path(".") else ""

        conversations.append(
            {
                "filename": str(rel_path),
                "directory": directory,
                "scenario_name": scenario["name"] if scenario else "unknown",
                "description": scenario["description"] if scenario else "",
                "timestamp": timestamp or filepath.stat().st_mtime,
                "turn_count": turn_count,
            }
        )

    conversations.sort(key=lambda c: c["timestamp"], reverse=True)
    return JSONResponse(conversations)


@app.get("/api/conversation/{filename:path}")
async def get_conversation(filename: str):
    """
    Return the turns array and matched scenario object for a conversation file.
    Validates against path traversal.
    """
    if "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = (OUTPUT_DIR / filename).resolve()
    if not filepath.is_relative_to(OUTPUT_DIR) or not filepath.exists():
        raise HTTPException(status_code=404, detail="Conversation not found")

    turns = []
    with open(filepath) as f:
        for line in f:
            if line.strip():
                turns.append(json.loads(line))

    scenario = match_scenario(filepath.name)
    return JSONResponse({"turns": turns, "scenario": scenario})


class SimulateRequest(BaseModel):
    scenario: str = "devops_backup_failure"
    model: str = "gpt-5-mini"
    max_turns: int = 30
    reflexio_enabled: bool = False
    reflexio_user_id: str = ""
    reflexio_agent_version: str = "demo-v1"
    mem0_enabled: bool = False
    mem0_user_id: str = ""


class ChatRequest(BaseModel):
    scenario: str
    model: str = "gpt-5-mini"
    message: str
    history: list[dict] = []
    reflexio_enabled: bool = False
    reflexio_user_id: str = ""
    reflexio_agent_version: str = "demo-v1"
    mem0_enabled: bool = False
    mem0_user_id: str = ""


def _build_reflexio_config(req: SimulateRequest) -> dict | None:
    """
    Build a reflexio_config dict from a SimulateRequest if Reflexio is enabled and client is logged in.

    Args:
        req (SimulateRequest): The simulation request

    Returns:
        dict | None: Config dict with client/user_id/agent_version, or None
    """
    if not req.reflexio_enabled or reflexio_client is None:
        return None
    return {
        "client": reflexio_client,
        "user_id": req.reflexio_user_id,
        "agent_version": req.reflexio_agent_version,
    }


def _build_mem0_config(req: SimulateRequest) -> dict | None:
    """
    Build a mem0_config dict from a SimulateRequest if mem0 is enabled and API key is available.

    Args:
        req (SimulateRequest): The simulation request

    Returns:
        dict | None: Config dict with api_key and user_id, or None
    """
    if not req.mem0_enabled:
        return None
    api_key = os.getenv("MEM0_API_KEY")
    if not api_key:
        return None
    return {
        "api_key": api_key,
        "user_id": req.mem0_user_id,
    }


@app.post("/api/simulate")
async def run_simulation(req: SimulateRequest):
    """
    Run a new conversation simulation using the specified scenario and model.
    Returns the new filename so the UI can load it.
    """
    if req.scenario not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {req.scenario}")

    try:
        rc = _build_reflexio_config(req)
        mc = _build_mem0_config(req)
        output_path = simulate(
            req.scenario,
            req.model,
            req.max_turns,
            None,
            reflexio_config=rc,
            mem0_config=mc,
        )
        return JSONResponse({"filename": output_path.name})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/simulate/stream")
async def run_simulation_stream(req: SimulateRequest):
    """
    Run a conversation simulation and stream each turn as a Server-Sent Event.

    Event types:
    - scenario: scenario metadata (sent first)
    - turn: each conversation turn as it's generated
    - done: final event with the output filename
    - error: if something fails mid-stream
    """
    if req.scenario not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {req.scenario}")

    rc = _build_reflexio_config(req)
    mc = _build_mem0_config(req)

    def event_generator():
        try:
            for item in simulate_stream(
                req.scenario,
                req.model,
                req.max_turns,
                reflexio_config=rc,
                mem0_config=mc,
            ):
                event_type = item["event"]
                data = json.dumps(item)
                yield f"event: {event_type}\ndata: {data}\n\n"
        except Exception as e:
            error_data = json.dumps({"event": "error", "message": str(e)})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Send a single user message and get the agent's response.
    The frontend sends the full conversation history with each request (stateless).

    Args:
        req (ChatRequest): The chat request with scenario, message, history, and optional context config
    """
    if req.scenario not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {req.scenario}")

    scenario = SCENARIOS[req.scenario]
    base_system_prompt = scenario.agent_system_prompt

    # Reconstruct agent_messages from history
    agent_messages = [{"role": "system", "content": base_system_prompt}]
    for turn in req.history:
        if turn["role"] == "customer":
            agent_messages.append({"role": "user", "content": turn["content"]})
        elif turn["role"] == "agent":
            agent_messages.append({"role": "assistant", "content": turn["content"]})

    # Optionally enhance system prompt with Reflexio/mem0 context
    turn_system_prompt = None
    if req.reflexio_enabled and reflexio_client:
        context = get_reflexio_context(
            {
                "client": reflexio_client,
                "user_id": req.reflexio_user_id,
                "agent_version": req.reflexio_agent_version,
            },
            req.message,
        )
        if context:
            enhanced_prompt = build_enhanced_prompt(base_system_prompt, context)
            agent_messages[0]["content"] = enhanced_prompt
            turn_system_prompt = enhanced_prompt
    elif req.mem0_enabled:
        api_key = os.getenv("MEM0_API_KEY")
        if api_key:
            context = get_mem0_context(
                {"api_key": api_key, "user_id": req.mem0_user_id}, req.message
            )
            if context:
                enhanced_prompt = base_system_prompt + context
                agent_messages[0]["content"] = enhanced_prompt
                turn_system_prompt = enhanced_prompt

    # Append the new user message
    agent_messages.append({"role": "user", "content": req.message})

    try:
        result = get_completion(req.model, agent_messages, tools=scenario.tools or None)
        turn_num = len(req.history) + 2  # +1 for new user msg, +1 for agent response
        turn_dict = {
            "turn": turn_num,
            "role": "agent",
            "content": result["content"],
            "labels": [],
        }
        if result["tool_interactions"]:
            turn_dict["tool_interactions"] = result["tool_interactions"]
        if turn_system_prompt:
            turn_dict["system_prompt"] = turn_system_prompt
            turn_dict["context_source"] = "reflexio" if req.reflexio_enabled else "mem0"
        return JSONResponse(turn_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Reflexio endpoints ---


class ReflexioLoginRequest(BaseModel):
    api_key: str
    reflexio_url: str = "http://localhost:8081"


class ReflexioPublishRequest(BaseModel):
    filename: str
    user_id: str
    agent_version: str = "demo-v1"
    source: str = ""


@app.post("/api/reflexio/login")
async def reflexio_login(req: ReflexioLoginRequest):
    """
    Connect to a Reflexio server using an API key and store the client for subsequent operations.
    """
    global reflexio_client
    try:
        client = ReflexioClient(api_key=req.api_key, url_endpoint=req.reflexio_url)
        reflexio_client = client
        return JSONResponse({"success": True})
    except Exception as e:
        logger.warning(f"Reflexio login failed: {e}")
        raise HTTPException(status_code=401, detail=f"Login failed: {e}")


@app.get("/api/reflexio/status")
async def reflexio_status():
    """Return whether a Reflexio client is currently logged in."""
    return JSONResponse({"logged_in": reflexio_client is not None})


@app.post("/api/reflexio/publish")
async def reflexio_publish(req: ReflexioPublishRequest):
    """
    Publish a conversation's turns as interactions to Reflexio.
    """
    if reflexio_client is None:
        raise HTTPException(status_code=401, detail="Not logged in to Reflexio")

    if "\\" in req.filename or ".." in req.filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = (OUTPUT_DIR / req.filename).resolve()
    if not filepath.is_relative_to(OUTPUT_DIR) or not filepath.exists():
        raise HTTPException(status_code=404, detail="Conversation file not found")

    try:
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
                            role=role,
                            content=turn["content"],
                            tools_used=tools_used,
                        )
                    )
                else:
                    interactions.append(
                        InteractionData(role=role, content=turn["content"])
                    )

        reflexio_client.publish_interaction(
            user_id=req.user_id,
            interactions=interactions,
            source=req.source,
            agent_version=req.agent_version,
            wait_for_response=True,
        )
        return JSONResponse(
            {"success": True, "message": f"Published {len(interactions)} interactions"}
        )
    except Exception as e:
        logger.warning(f"Reflexio publish failed: {e}")
        raise HTTPException(status_code=500, detail=f"Publish failed: {e}")


# --- mem0 endpoints ---


class Mem0PublishRequest(BaseModel):
    filename: str
    user_id: str = "demo-user"


@app.post("/api/mem0/publish")
async def mem0_publish(req: Mem0PublishRequest):
    """
    Publish all interactions from a conversation to mem0 as memories.

    Args:
        req (Mem0PublishRequest): The publish request with filename and user_id
    """
    api_key = os.getenv("MEM0_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500, detail="MEM0_API_KEY not configured in demo/.env"
        )

    if "\\" in req.filename or ".." in req.filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = (OUTPUT_DIR / req.filename).resolve()
    if not filepath.is_relative_to(OUTPUT_DIR) or not filepath.exists():
        raise HTTPException(status_code=404, detail="Conversation file not found")

    try:
        from mem0 import MemoryClient

        client = MemoryClient(api_key=api_key)

        # Read conversation turns and format as messages
        messages = []
        with open(filepath) as f:
            for line in f:
                if not line.strip():
                    continue
                turn = json.loads(line)
                role = "user" if turn["role"] == "customer" else "assistant"
                messages.append({"role": role, "content": turn["content"]})

        if not messages:
            raise HTTPException(
                status_code=400, detail="No interactions found in conversation"
            )

        result = client.add(
            messages, user_id=req.user_id, version="v2", output_format="v1.1"
        )
        return JSONResponse(
            {
                "success": True,
                "message": f"Published {len(messages)} messages to mem0",
                "result": result,
            }
        )
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="mem0ai package not installed. Run: pip install mem0ai",
        )
    except Exception as e:
        logger.warning(f"mem0 publish failed: {e}")
        raise HTTPException(status_code=500, detail=f"Publish failed: {e}")


# --- Evaluation endpoints ---


class EvaluateRequest(BaseModel):
    baseline_file: str
    enhanced_file: str
    judge_model: str = "gpt-5-mini"


class RunComparisonRequest(BaseModel):
    scenario: str
    model: str = "gpt-5-mini"
    judge_model: str = "gpt-5-mini"
    max_turns: int = 30
    reflexio_user_id: str = ""
    reflexio_agent_version: str = "demo-v1"
    skip_publish: bool = False


@app.post("/api/evaluate")
async def evaluate_pair(req: EvaluateRequest):
    """
    Evaluate a pair of existing conversations and save the result.
    """
    for fname in [req.baseline_file, req.enhanced_file]:
        if "\\" in fname or ".." in fname:
            raise HTTPException(status_code=400, detail=f"Invalid filename: {fname}")

    baseline_path = (OUTPUT_DIR / req.baseline_file).resolve()
    enhanced_path = (OUTPUT_DIR / req.enhanced_file).resolve()

    if not baseline_path.is_relative_to(OUTPUT_DIR) or not baseline_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Baseline file not found: {req.baseline_file}"
        )
    if not enhanced_path.is_relative_to(OUTPUT_DIR) or not enhanced_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Enhanced file not found: {req.enhanced_file}"
        )

    try:
        result = compare_conversations(baseline_path, enhanced_path, req.judge_model)
        eval_path = save_evaluation(result)
        return JSONResponse(
            {
                "success": True,
                "evaluation": result.model_dump(),
                "evaluation_file": eval_path.name,
            }
        )
    except Exception as e:
        logger.warning(f"Evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {e}")


@app.post("/api/compare/stream")
async def run_comparison_stream(req: RunComparisonRequest):
    """
    Stream a full comparison pipeline via SSE: baseline sim -> publish -> enhanced sim -> evaluate.
    """
    if req.scenario not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {req.scenario}")
    if reflexio_client is None:
        raise HTTPException(status_code=401, detail="Not logged in to Reflexio")

    def event_generator():
        try:
            # Phase 1: Baseline simulation
            yield _sse_event(
                "status",
                {"phase": "baseline", "message": "Starting baseline simulation..."},
            )

            baseline_turns = []
            for item in simulate_stream(req.scenario, req.model, req.max_turns):
                if item["event"] == "turn":
                    baseline_turns.append(item)
                    yield _sse_event(
                        "turn", {**item, "phase": "baseline"}
                    )
                elif item["event"] == "done":
                    baseline_filename = item["filename"]
                elif item["event"] == "scenario":
                    yield _sse_event("scenario", item)

            # Phase 2: Publish to Reflexio
            if not req.skip_publish:
                yield _sse_event(
                    "status",
                    {"phase": "publish", "message": "Publishing baseline to Reflexio..."},
                )
                baseline_path = OUTPUT_DIR / baseline_filename
                interactions = []
                with open(baseline_path) as f:
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
                                    role=role,
                                    content=turn["content"],
                                    tools_used=tools_used,
                                )
                            )
                        else:
                            interactions.append(
                                InteractionData(role=role, content=turn["content"])
                            )
                reflexio_client.publish_interaction(
                    user_id=req.reflexio_user_id or "demo-user",
                    interactions=interactions,
                    source="demo-comparison",
                    agent_version=req.reflexio_agent_version,
                    wait_for_response=True,
                )
                yield _sse_event(
                    "status",
                    {"phase": "publish", "message": f"Published {len(interactions)} interactions"},
                )
            else:
                yield _sse_event(
                    "status",
                    {"phase": "publish", "message": "Skipping publish (skip_publish=true)"},
                )

            # Phase 3: Enhanced simulation (with Reflexio)
            yield _sse_event(
                "status",
                {"phase": "enhanced", "message": "Starting enhanced simulation with Reflexio..."},
            )
            rc = {
                "client": reflexio_client,
                "user_id": req.reflexio_user_id or "demo-user",
                "agent_version": req.reflexio_agent_version,
            }

            enhanced_filename = None
            for item in simulate_stream(
                req.scenario, req.model, req.max_turns, reflexio_config=rc
            ):
                if item["event"] == "turn":
                    yield _sse_event(
                        "turn", {**item, "phase": "enhanced"}
                    )
                elif item["event"] == "done":
                    enhanced_filename = item["filename"]

            # Phase 4: Evaluation
            yield _sse_event(
                "status",
                {"phase": "evaluation", "message": "Evaluating conversations..."},
            )
            baseline_path = OUTPUT_DIR / baseline_filename
            enhanced_path = OUTPUT_DIR / enhanced_filename
            result = compare_conversations(
                baseline_path, enhanced_path, req.judge_model
            )
            eval_path = save_evaluation(result)

            yield _sse_event("evaluation", result.model_dump())
            yield _sse_event(
                "done",
                {
                    "evaluation_file": eval_path.name,
                    "baseline_file": baseline_filename,
                    "enhanced_file": enhanced_filename,
                },
            )

        except Exception as e:
            logger.exception("Comparison stream failed")
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _sse_event(event_type: str, data: dict) -> str:
    """Format a dict as an SSE event string."""
    payload = {"event": event_type, **data}
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


@app.get("/api/evaluations")
async def list_evaluations():
    """List all saved evaluation results."""
    EVALUATIONS_DIR.mkdir(parents=True, exist_ok=True)
    evaluations = []
    for filepath in sorted(EVALUATIONS_DIR.glob("*_eval.json"), reverse=True):
        try:
            result = load_evaluation(filepath)
            evaluations.append(
                {
                    "filename": filepath.name,
                    "scenario_name": result.scenario_name,
                    "winner": result.winner,
                    "baseline_score": result.baseline_metrics.overall_score,
                    "enhanced_score": result.enhanced_metrics.overall_score,
                    "evaluated_at": result.evaluated_at,
                    "judge_model": result.judge_model,
                }
            )
        except Exception as e:
            logger.warning(f"Failed to load evaluation {filepath.name}: {e}")
    return JSONResponse(evaluations)


@app.get("/api/evaluation/{filename}")
async def get_evaluation(filename: str):
    """Get a specific evaluation result."""
    if "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    filepath = (EVALUATIONS_DIR / filename).resolve()
    if not filepath.is_relative_to(EVALUATIONS_DIR) or not filepath.exists():
        raise HTTPException(status_code=404, detail="Evaluation not found")
    try:
        result = load_evaluation(filepath)
        return JSONResponse(result.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load evaluation: {e}")


@app.delete("/api/evaluation/{filename}")
async def delete_evaluation(filename: str):
    """Delete an evaluation result."""
    if "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    filepath = (EVALUATIONS_DIR / filename).resolve()
    if not filepath.is_relative_to(EVALUATIONS_DIR) or not filepath.exists():
        raise HTTPException(status_code=404, detail="Evaluation not found")
    filepath.unlink()
    return JSONResponse({"success": True})


if __name__ == "__main__":
    uvicorn.run(
        "serve_viewer:app",
        host="0.0.0.0",
        port=8083,
        reload=True,
        reload_dirs=[str(DEMO_DIR)],
    )
