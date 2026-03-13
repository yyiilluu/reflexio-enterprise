from pydantic import BaseModel


class Prompt(BaseModel):
    """Individual prompt version structure that matches the JSON schema"""

    created_at: int
    content: str
    variables: list[str]


class PromptBank(BaseModel):
    """Complete prompt file structure"""

    prompt_id: str
    active_version: str
    created_at: int
    last_updated: int
    description: str | None
    versions: dict[str, Prompt]
