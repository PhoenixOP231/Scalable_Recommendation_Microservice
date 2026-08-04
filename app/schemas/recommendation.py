from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class Filters(BaseModel):
    min_price: Optional[float] = None
    max_price: Optional[float] = None

class RecommendationRequest(BaseModel):
    user_id: str
    limit: int = Field(10, ge=1, le=100)
    seed_item_ids: List[str] = []
    excluded_categories: List[str] = []
    filters: Optional[Filters] = None
    diversity: float = Field(0.25, ge=0.0, le=1.0)
    cache_ttl_seconds: int = Field(60, ge=0)

class ExplainableScore(BaseModel):
    vector_score: float
    popularity_score: float
    freshness_score: float
    final_score: float
    reason: str

class RecommendedItem(BaseModel):
    item_id: str
    title: str
    category: str
    scores: ExplainableScore

class RecommendationResponse(BaseModel):
    request_id: str
    user_id: str
    recommendations: List[RecommendedItem]
    cache_hit: bool
    retrieval_latency_ms: float
    total_latency_ms: float
    candidate_count: int
    generated_at: datetime
