"""
System prompt templates for AppWorld benchmark agents.

Contains the base ReAct-style prompt for code-generation agents and
context injection utilities for Reflexio-enhanced agents.
"""

SYSTEM_PROMPT_TEMPLATE = """\
You are an autonomous agent that solves tasks by writing Python code.
You operate in the AppWorld environment where you interact with 9 simulated apps
(Amazon, Gmail, Spotify, Venmo, File Manager, Phone, Reminders, Notes, Calendar)
through their REST APIs via a pre-configured `apis` object.

## Your Goal
{task_instruction}

## Supervisor Information
{supervisor_info}

## Available APIs
{api_docs}

## Rules
1. Write Python code to accomplish the task. Each response must contain exactly ONE
   Python code block (```python ... ```).
2. You have access to a pre-configured `apis` object that provides methods for all 9 apps.
   Use `apis.<app_name>.<method_name>(...)` to call API endpoints.
3. ALWAYS check return values. API calls may return error responses — handle them.
4. Use `apis.api_docs.get_api_details(api_name)` to look up exact parameters for an API
   if you are unsure.
5. When the task is fully complete, call `apis.supervisor.complete_task()` as the LAST
   action in your code.
6. Do NOT call `complete_task()` until you are confident ALL task requirements are met.
7. If you encounter an error, analyze it and try a different approach — do NOT repeat
   the same failing code.
8. You may use standard Python libraries (json, datetime, re, etc.) but no external packages.
9. Keep your code concise and focused. Avoid unnecessary print statements.
10. When searching for items (products, songs, etc.), use broad searches first, then filter results.

## Output Format
Respond with a single Python code block. Do not include any text outside the code block.

```python
# Your code here
```
"""

BEHAVIOR_REMINDER = (
    "**Note: You have information about the user from context and behavior corrections "
    "from past interactions in this prompt. Before responding, make use of known user "
    "information and follow corrections in current situation if applicable.**\n\n"
)


def build_system_prompt(
    task_instruction: str,
    supervisor_info: str,
    api_docs: str,
) -> str:
    """
    Build the base system prompt for the AppWorld agent.

    Args:
        task_instruction (str): The task description from AppWorld
        supervisor_info (str): Supervisor name, email, and other persona details
        api_docs (str): Compressed API documentation string

    Returns:
        str: Formatted system prompt
    """
    return SYSTEM_PROMPT_TEMPLATE.format(
        task_instruction=task_instruction,
        supervisor_info=supervisor_info,
        api_docs=api_docs,
    )


def build_enhanced_prompt(base_system_prompt: str, context: str) -> str:
    """
    Build an enhanced system prompt by prepending a behavior reminder and Reflexio context.

    Follows the pattern from demo/simulate_conversation.py:build_enhanced_prompt().

    Args:
        base_system_prompt (str): The original agent system prompt
        context (str): The Reflexio context block (profiles + feedback + skills)

    Returns:
        str: Enhanced prompt with reminder at top and context at bottom
    """
    return BEHAVIOR_REMINDER + context + "\n\n" + base_system_prompt
