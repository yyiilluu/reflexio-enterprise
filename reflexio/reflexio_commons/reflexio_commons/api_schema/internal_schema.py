# ==============================
# Internal data models
# for only internal data representation
# ==============================
from reflexio_commons.api_schema.service_schemas import Request, Interaction
from pydantic import BaseModel


class RequestInteractionDataModel(BaseModel):
    session_id: str
    request: Request
    interactions: list[Interaction]
