"""
ReflexioAppWorldAgent — AppWorld agent enhanced with Reflexio context injection.

Extends BaseAppWorldAgent by fetching relevant profiles, feedbacks, and skills
from Reflexio and injecting them into the system prompt at task start.
"""

import logging

from benchmarks.appworld.agent.base_agent import BaseAppWorldAgent
from benchmarks.appworld.agent.prompts import build_enhanced_prompt
from benchmarks.appworld.config import ReflexioConfig
from benchmarks.appworld.integration.context_builder import fetch_reflexio_context
from benchmarks.appworld.integration.reflexio_bridge import get_user_id

logger = logging.getLogger(__name__)


class ReflexioAppWorldAgent(BaseAppWorldAgent):
    """
    AppWorld agent enhanced with Reflexio memory context.

    Fetches relevant profiles, feedbacks, and skills from Reflexio using the
    task instruction as a search query, then injects the context into the
    system prompt once at task start.

    Args:
        model (str): LLM model identifier
        client: ReflexioClient instance
        reflexio_config (ReflexioConfig): Reflexio search parameters
        max_steps (int): Maximum agent steps per task
        temperature (float): LLM sampling temperature
    """

    def __init__(
        self,
        model: str = "minimax/MiniMax-M2.5",
        client=None,
        reflexio_config: ReflexioConfig | None = None,
        max_steps: int = 20,
        temperature: float = 0.0,
    ):
        super().__init__(model=model, max_steps=max_steps, temperature=temperature)
        self.client = client
        self.reflexio_config = reflexio_config or ReflexioConfig()

    def build_system_prompt(self, world) -> str:
        """
        Build the system prompt with Reflexio context injection.

        Fetches relevant context from Reflexio using the task instruction
        as the search query, then prepends it to the base system prompt.

        Args:
            world: AppWorld instance with task and API docs

        Returns:
            str: Enhanced system prompt with Reflexio context
        """
        base_prompt = super().build_system_prompt(world)

        if not self.client:
            logger.warning("No Reflexio client configured, using base prompt")
            return base_prompt

        # Determine user ID from supervisor email
        supervisor_email = ""
        if hasattr(world.task, "supervisor") and world.task.supervisor:
            supervisor_email = getattr(world.task.supervisor, "email", "")
        user_id = get_user_id(supervisor_email)

        context = fetch_reflexio_context(
            client=self.client,
            query=world.task.instruction,
            user_id=user_id,
            agent_version=self.reflexio_config.agent_version,
            config=self.reflexio_config,
        )

        if context:
            logger.info(
                "Injecting Reflexio context for task %s (user=%s)",
                world.task.task_id,
                user_id,
            )
            return build_enhanced_prompt(base_prompt, context)

        logger.info("No Reflexio context found for task %s", world.task.task_id)
        return base_prompt
