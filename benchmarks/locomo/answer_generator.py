"""LLM answer generation with context."""

from __future__ import annotations

import litellm

ANSWER_PROMPT_TEMPLATE = """\
Below is context from a conversation between {speaker_a} and {speaker_b}.
Answer the question based ONLY on the provided context.
If the information is not available, say "I don't have enough information".
Answer in the form of a short phrase.

Context:
{context}

Question: {question}"""

NO_CONTEXT_PROMPT_TEMPLATE = """\
Answer the following question. If you don't know the answer, say "I don't have enough information".
Answer in the form of a short phrase.

Question: {question}"""


def generate_answer(
    question: str,
    context: str,
    speaker_a: str,
    speaker_b: str,
    model: str,
) -> str:
    """
    Generate an answer to a QA question using the provided context.

    Args:
        question (str): The question to answer
        context (str): Context to base the answer on (empty string for no_context)
        speaker_a (str): Name of speaker A
        speaker_b (str): Name of speaker B
        model (str): LiteLLM model identifier

    Returns:
        str: Generated answer
    """
    if not context.strip():
        prompt = NO_CONTEXT_PROMPT_TEMPLATE.format(question=question)
    else:
        prompt = ANSWER_PROMPT_TEMPLATE.format(
            speaker_a=speaker_a,
            speaker_b=speaker_b,
            context=context,
            question=question,
        )

    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    return response.choices[0].message.content.strip()
