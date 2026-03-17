"""
Runs a single AppWorld task with a given agent and returns structured results.
"""

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """
    Result of running a single AppWorld task.

    Args:
        task_id (str): AppWorld task identifier
        passed (bool): Whether all evaluation assertions passed
        completed (bool): Whether the agent called complete_task()
        total_steps (int): Number of steps the agent took
        elapsed_seconds (float): Wall-clock time for the task
        error_count (int): Number of execution errors during the task
        eval_details (dict): Raw evaluation output from AppWorld
        trace_file (str): Path to the saved trace file
    """

    task_id: str
    passed: bool = False
    completed: bool = False
    total_steps: int = 0
    elapsed_seconds: float = 0.0
    error_count: int = 0
    eval_details: dict = field(default_factory=dict)
    trace_file: str = ""


def run_task(
    task_id: str,
    agent,
    experiment_name: str,
    output_dir: Path | None = None,
) -> TaskResult:
    """
    Run a single AppWorld task with the given agent and evaluate the result.

    Creates an AppWorld instance, lets the agent solve the task, evaluates
    the result, and saves the execution trace.

    Args:
        task_id (str): AppWorld task identifier to run
        agent: BaseAppWorldAgent (or subclass) instance
        experiment_name (str): Name for the AppWorld experiment (groups outputs)
        output_dir (Path | None): Directory to save trace files (None = skip saving)

    Returns:
        TaskResult: Structured result with pass/fail, step count, and trace path
    """
    from appworld import AppWorld

    logger.info("Starting task %s (experiment=%s)", task_id, experiment_name)
    start_time = time.time()

    try:
        with AppWorld(task_id=task_id, experiment_name=experiment_name) as world:
            # Run the agent
            trace = agent.solve(world)

            # Evaluate
            try:
                eval_result = world.evaluate()
                passed = (
                    eval_result.passed
                    if hasattr(eval_result, "passed")
                    else bool(eval_result)
                )
                eval_details = (
                    eval_result.__dict__
                    if hasattr(eval_result, "__dict__")
                    else {"result": str(eval_result)}
                )
            except Exception:
                logger.exception("Evaluation failed for task %s", task_id)
                passed = False
                eval_details = {"error": "evaluation_failed"}

            # Count errors
            error_count = sum(1 for step in trace.steps if step.error)

            result = TaskResult(
                task_id=task_id,
                passed=passed,
                completed=trace.completed,
                total_steps=trace.total_steps,
                elapsed_seconds=time.time() - start_time,
                error_count=error_count,
                eval_details=eval_details,
            )

            # Save trace
            if output_dir:
                result.trace_file = _save_trace(trace, result, output_dir)

            logger.info(
                "Task %s: passed=%s, steps=%d, errors=%d, time=%.1fs",
                task_id,
                passed,
                trace.total_steps,
                error_count,
                result.elapsed_seconds,
            )
            return result

    except Exception:
        logger.exception("Fatal error running task %s", task_id)
        return TaskResult(
            task_id=task_id,
            passed=False,
            elapsed_seconds=time.time() - start_time,
            eval_details={"error": "task_execution_failed"},
        )


def _save_trace(trace, result: TaskResult, output_dir: Path) -> str:
    """
    Save an agent trace and task result to a JSON file.

    Args:
        trace: AgentTrace object
        result (TaskResult): Task evaluation result
        output_dir (Path): Directory to save the file

    Returns:
        str: Path to the saved file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / f"{trace.task_id}.json"

    data = {
        "task_id": trace.task_id,
        "result": asdict(result),
        "trace": {
            "system_prompt": trace.system_prompt,
            "completed": trace.completed,
            "total_steps": trace.total_steps,
            "elapsed_seconds": trace.elapsed_seconds,
            "steps": [asdict(s) for s in trace.steps],
        },
    }

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)

    return str(filepath)
