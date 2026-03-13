# ==============================
# Internal data models
# for only internal data representation
# ==============================
from pydantic import BaseModel

from reflexio_commons.api_schema.service_schemas import Interaction, Request


class RequestInteractionDataModel(BaseModel):
    session_id: str
    request: Request
    interactions: list[Interaction]
