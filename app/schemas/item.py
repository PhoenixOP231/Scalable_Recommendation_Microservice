from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

class ItemBase(BaseModel):
    id: str = Field(..., description="Unique string ID for the item (will be UUID-mapped in Qdrant)")
    title: str
    description: str = ""
    category: str = ""
    tags: List[str] = []
    image_url: Optional[str] = None
    price: float = 0.0
    popularity_score: float = 0.0
    created_at: datetime
    is_active: bool = True

class ItemCreate(ItemBase):
    pass

class Item(ItemBase):
    pass
