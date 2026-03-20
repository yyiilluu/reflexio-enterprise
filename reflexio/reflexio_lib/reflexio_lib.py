"""Reflexio facade — assembled from domain mixins."""

from reflexio.reflexio_lib._config import ConfigMixin
from reflexio.reflexio_lib._dashboard import DashboardMixin
from reflexio.reflexio_lib._feedback import FeedbackMixin
from reflexio.reflexio_lib._generation import GenerationMixin
from reflexio.reflexio_lib._interactions import InteractionsMixin
from reflexio.reflexio_lib._operations import OperationsMixin
from reflexio.reflexio_lib._profiles import ProfilesMixin
from reflexio.reflexio_lib._raw_feedback import RawFeedbackMixin
from reflexio.reflexio_lib._search import SearchMixin
from reflexio.reflexio_lib._skills import SkillsMixin


class Reflexio(
    InteractionsMixin,
    ProfilesMixin,
    FeedbackMixin,
    RawFeedbackMixin,
    SkillsMixin,
    ConfigMixin,
    GenerationMixin,
    OperationsMixin,
    DashboardMixin,
    SearchMixin,
):
    """Synchronous facade providing a unified API for all Reflexio operations."""
