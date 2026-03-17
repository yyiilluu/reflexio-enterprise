# AppWorld Benchmark

Evaluates whether Reflexio's persistent memory (profiles, feedbacks, skills) improves an LLM agent's task success rate on the [AppWorld](https://github.com/stonybrooknlp/appworld) benchmark.

## AppWorld Dataset

AppWorld is a benchmark of **750 tasks** across **9 simulated apps**: Amazon, Gmail, Spotify, Venmo, File Manager, Phone, Reminders, Notes, and Calendar. Agents write Python code to interact with app APIs (457 endpoints total) to complete tasks on behalf of supervisor users.

- **Paper**: [AppWorld: A Controllable World of Apps and People for Benchmarking Interactive Coding Agents](https://arxiv.org/abs/2407.18901) (ACL 2024)
- **GitHub**: [stonybrooknlp/appworld](https://github.com/stonybrooknlp/appworld)
- **Splits**: `dev` (development), `test_normal` (standard test), `test_challenge` (hard test)
- **Metrics**: TGC (Task Goal Completion — % of tasks passing all assertions), SGC (Scenario Goal Completion — % of scenarios where all task instantiations pass)

## What This Benchmark Does

Tests whether Reflexio's memory system improves an agent's task success rate through a four-phase pipeline:

1. **Baseline** — Run all tasks with `BaseAppWorldAgent` (stateless, no memory)
2. **Publish** — Convert baseline traces to Reflexio interactions and publish for profile/feedback extraction
3. **Enhanced** — Run the same tasks with `ReflexioAppWorldAgent` (injects relevant profiles, feedbacks, and skills from Reflexio)
4. **Compare** — Compute TGC/SGC deltas, McNemar's statistical significance test, and per-task confusion matrix

### Module Overview

| Module | Description |
|---|---|
| `run_benchmark.py` | Unified CLI entry point — runs full pipeline end-to-end |
| `config.py` | `ExperimentConfig` and `ReflexioConfig` dataclasses |
| `agent/base_agent.py` | `BaseAppWorldAgent` — stateless code-generation agent |
| `agent/reflexio_agent.py` | `ReflexioAppWorldAgent` — extends base agent with Reflexio context injection |
| `agent/prompts.py` | System and step prompt templates |
| `runner/experiment_runner.py` | Orchestrates experiments: `run_baseline()`, `publish_to_reflexio()`, `run_enhanced()` |
| `runner/task_runner.py` | Runs a single task in an AppWorld sandbox |
| `integration/reflexio_bridge.py` | Converts traces to Reflexio `InteractionData` and publishes |
| `integration/context_builder.py` | Builds Reflexio context (profiles + feedbacks + skills) for enhanced agent |
| `evaluation/metrics.py` | TGC, SGC, and `compute_comparison()` |
| `evaluation/analysis.py` | McNemar's test, confusion matrix, `generate_report()` |
| `scripts/run_baseline.py` | Standalone baseline script |
| `scripts/run_enhanced.py` | Standalone enhanced script |
| `scripts/run_comparison.py` | Standalone comparison script |

## How to Run

### Prerequisites

1. **AppWorld** installed with data downloaded
2. **Reflexio server** running (not needed for `--baseline-only`)
3. **API keys**: `REFLEXIO_API_KEY` in `.env`, plus an LLM API key for your chosen model

### Installation

```bash
# Install AppWorld (if not already installed)
pip install appworld
appworld install
appworld download data

# Ensure benchmark dependencies are available
cd /path/to/reflexio
uv sync
```

### Run Examples

```bash
# Full pipeline (baseline -> publish -> enhanced -> compare)
python benchmarks/appworld/run_benchmark.py

# Baseline only (no Reflexio server needed)
python benchmarks/appworld/run_benchmark.py --baseline-only

# Skip publishing (reuse existing Reflexio data from a prior run)
python benchmarks/appworld/run_benchmark.py --skip-publish

# Run specific tasks
python benchmarks/appworld/run_benchmark.py --task-ids 123_1 456_2

# Use a different model and dataset split
python benchmarks/appworld/run_benchmark.py --model gpt-4o --dataset test_normal --max-steps 30

# Debug logging
python benchmarks/appworld/run_benchmark.py --verbose
```

### CLI Arguments

| Argument | Default | Description |
|---|---|---|
| `--dataset` | `dev` | AppWorld split (`dev`, `test_normal`, `test_challenge`) |
| `--model` | `minimax/MiniMax-M2.5` | LiteLLM model identifier |
| `--max-steps` | `20` | Max agent reasoning steps per task |
| `--task-ids` | all | Specific task IDs to run |
| `--reflexio-url` | `http://localhost:8081` | Reflexio server URL |
| `--reflexio-api-key` | `$REFLEXIO_API_KEY` | Reflexio API key |
| `--skip-publish` | `false` | Skip publishing traces to Reflexio |
| `--baseline-only` | `false` | Run baseline only (no Reflexio needed) |
| `--output-dir` | `benchmarks/appworld/output` | Output directory |
| `--verbose` | `false` | Enable debug logging |

### Output

Results are saved to the output directory (default: `benchmarks/appworld/output/`):

```
output/
├── baseline/
│   ├── summary.json          # Aggregate metrics (TGC, SGC, etc.)
│   └── <task_id>.json        # Per-task trace and result
├── reflexio_enhanced/
│   ├── summary.json
│   └── <task_id>.json
├── comparison.json            # Full comparison metrics (JSON)
└── report.txt                 # Human-readable comparison report
```
