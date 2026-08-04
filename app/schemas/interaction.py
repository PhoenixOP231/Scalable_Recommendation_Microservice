from pydantic import BaseModel
from datetime import datetime
from enum import Enum

class InteractionType(str, Enum):
    VIEW = "view"
    CLICK = "click"
    SAVE = "save"
    PURCHASE = "purchase"

class InteractionCreate(BaseModel):
    user_id: str
    item_id: str
    interaction_type: InteractionType
    timestamp: datetime | None = None
