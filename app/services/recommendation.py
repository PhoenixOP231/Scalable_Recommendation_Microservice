import json
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import math
import logging
import time

from app.schemas.recommendation import RecommendationRequest, RecommendationResponse, RecommendedItem, ExplainableScore
from app.repositories.vector import VectorRepository
from app.repositories.cache import CacheRepository
from app.schemas.interaction import InteractionType
from app.core.settings import settings

logger = logging.getLogger("app")

ALGO_VERSION = "v1"

INTERACTION_WEIGHTS = {
    InteractionType.VIEW.value: 1.0,
    InteractionType.CLICK.value: 2.0,
    InteractionType.SAVE.value: 3.0,
    InteractionType.PURCHASE.value: 4.0,
}

class RecommendationService:
    def __init__(
        self, 
        vector_repo: VectorRepository, 
        cache_repo: CacheRepository
    ):
        self.vector_repo = vector_repo
        self.cache_repo = cache_repo

    def _generate_cache_key(
        self, 
        request: RecommendationRequest, 
        user_version: int, 
        catalog_version: int
    ) -> str:
        req_dict = request.model_dump(mode='json')
        req_dict["user_version"] = user_version
        req_dict["catalog_version"] = catalog_version
        req_dict["algo_version"] = ALGO_VERSION
        
        # Sort keys to ensure deterministic JSON string
        json_str = json.dumps(req_dict, sort_keys=True)
        hash_digest = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
        return f"rec:{hash_digest}"

    def _cosine_sim(self, v1: List[float], v2: List[float]) -> float:
        dot = sum(a*b for a,b in zip(v1, v2))
        norm1 = math.sqrt(sum(a*a for a in v1))
        norm2 = math.sqrt(sum(b*b for b in v2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def _compute_freshness(self, created_at_iso: str) -> float:
        try:
            # Parse ISO format, handle Z
            if created_at_iso.endswith("Z"):
                created_at_iso = created_at_iso[:-1] + "+00:00"
            created_at = datetime.fromisoformat(created_at_iso)
            now = datetime.now(timezone.utc)
            delta_days = (now - created_at).days
            # Exponential decay, half-life of 30 days
            return math.exp(-0.693 * delta_days / 30.0)
        except Exception:
            return 0.0

    def _normalize_popularity(self, score: float) -> float:
        # Assuming popularity is 0-100 or something, we use a simple sigmoid-like clamp
        # Or simply clamp between 0 and 1 if already in 0-1
        return max(0.0, min(1.0, score / 100.0 if score > 1.0 else score))

    async def get_recommendations(
        self,
        request: RecommendationRequest,
        demo_history: Optional[List[Dict[str, Any]]] = None
    ) -> RecommendationResponse:
        start_time = time.time()
        
        # 1. Fetch versions
        catalog_version = await self.cache_repo.get_catalog_version()
        
        # For user version, we could do a dummy call if we don't store it explicitly,
        # but let's just get the interactions and hash them as a proxy for version if not using strict versioning,
        # or we just get the interactions directly. 
        if demo_history is not None:
            interactions = demo_history
        else:
            interactions = await self.cache_repo.get_user_interactions(request.user_id)
        
        user_version = len(interactions) # Simple proxy for user version based on history length if counter missing
        
        # 2. Check Cache
        cache_key = self._generate_cache_key(request, user_version, catalog_version)
        cached_response = await self.cache_repo.get_recommendation(cache_key)
        
        if cached_response:
            total_time = (time.time() - start_time) * 1000
            # Update latencies
            cached_response["total_latency_ms"] = total_time
            cached_response["cache_hit"] = True
            logger.info(f"Cache hit for key {cache_key}", extra={"request_id": "TODO", "user_id": request.user_id})
            return RecommendationResponse(**cached_response)

        # 3. Build Preference Vector
        seen_item_ids = set()
        weighted_vector = [0.0] * settings.EMBEDDING_DIMENSIONS
        total_weight = 0.0
        
        # Collect item IDs to fetch vectors
        item_ids_to_fetch = set(request.seed_item_ids)
        for interaction in interactions:
            item_ids_to_fetch.add(interaction["item_id"])
            seen_item_ids.add(interaction["item_id"])
            
        vectors_dict = await self.vector_repo.get_items_vectors(list(item_ids_to_fetch))
        
        # Apply interactions
        for interaction in interactions:
            item_id = interaction["item_id"]
            if item_id in vectors_dict:
                weight = INTERACTION_WEIGHTS.get(interaction.get("interaction_type"), 1.0)
                vec = vectors_dict[item_id]
                for i in range(len(weighted_vector)):
                    weighted_vector[i] += vec[i] * weight
                total_weight += weight
                
        # Apply explicit seeds (strong weight)
        seed_weight = 5.0
        for seed_id in request.seed_item_ids:
            if seed_id in vectors_dict:
                vec = vectors_dict[seed_id]
                for i in range(len(weighted_vector)):
                    weighted_vector[i] += vec[i] * seed_weight
                total_weight += seed_weight
                seen_item_ids.add(seed_id)
                
        retrieval_start = time.time()
        
        # Determine query vector and fallback
        candidates = []
        is_fallback = False
        
        min_price = request.filters.min_price if request.filters else None
        max_price = request.filters.max_price if request.filters else None
        
        if total_weight > 0:
            # Normalize user vector
            weighted_vector = [v / total_weight for v in weighted_vector]
            # Fetch from Qdrant
            # Fetch more than limit to allow reranking and MMR
            fetch_limit = min(request.limit * 3, 100)
            candidates = await self.vector_repo.search(
                query_vector=weighted_vector,
                limit=fetch_limit,
                exclude_item_ids=list(seen_item_ids),
                exclude_categories=request.excluded_categories,
                min_price=min_price,
                max_price=max_price
            )
        else:
            is_fallback = True
            # Fallback: user has no history. We fetch based on a zero vector (if allowed) or fetch popular
            # In Qdrant, we can search with a dummy zero vector or random vector, but Qdrant requires valid vector.
            # Let's use a zero vector of correct dimensions.
            dummy_vector = [0.0] * settings.EMBEDDING_DIMENSIONS
            dummy_vector[0] = 1.0 # Need non-zero for cosine
            fetch_limit = min(request.limit * 3, 100)
            candidates = await self.vector_repo.search(
                query_vector=dummy_vector,
                limit=fetch_limit,
                exclude_item_ids=list(seen_item_ids),
                exclude_categories=request.excluded_categories,
                min_price=min_price,
                max_price=max_price
            )

        retrieval_latency = (time.time() - retrieval_start) * 1000
        
        # 4. Reranking
        scored_candidates = []
        for cand in candidates:
            semantic_score = cand.get("vector_score", 0.0)
            popularity_score = self._normalize_popularity(cand.get("popularity_score", 0.0))
            freshness_score = self._compute_freshness(cand.get("created_at"))
            
            # Weights
            if is_fallback:
                final_score = 0.7 * popularity_score + 0.3 * freshness_score
                reason = "Popular and fresh item"
            else:
                final_score = 0.6 * semantic_score + 0.3 * popularity_score + 0.1 * freshness_score
                reason = "Similar to your interests"
                
            scored_candidates.append({
                "item": cand,
                "scores": ExplainableScore(
                    vector_score=semantic_score,
                    popularity_score=popularity_score,
                    freshness_score=freshness_score,
                    final_score=final_score,
                    reason=reason
                )
            })
            
        scored_candidates.sort(key=lambda x: x["scores"].final_score, reverse=True)
        
        # 5. MMR Diversity
        final_list = []
        diversity_lambda = 1.0 - request.diversity
        
        # We need vectors for MMR. For fallback we might not have them easily if not returned by search.
        # But Qdrant search doesn't return vectors by default (with_payload=True doesn't include vector unless with_vectors=True).
        # We can just skip MMR if diversity == 0 or we do a simpler diversity check based on category.
        # Let's fetch vectors if diversity > 0 and not fallback.
        
        if request.diversity > 0.0 and scored_candidates:
            # Fetch vectors for the candidates
            cand_ids = [c["item"]["item_id"] for c in scored_candidates]
            cand_vectors = await self.vector_repo.get_items_vectors(cand_ids)
            
            unselected = scored_candidates.copy()
            selected = []
            
            while unselected and len(selected) < request.limit:
                if not selected:
                    # Pick max final score
                    best = unselected.pop(0)
                    selected.append(best)
                else:
                    best_score = -float('inf')
                    best_idx = 0
                    for i, cand in enumerate(unselected):
                        cand_id = cand["item"]["item_id"]
                        cand_vec = cand_vectors.get(cand_id)
                        
                        max_sim_to_selected = 0.0
                        if cand_vec:
                            for sel in selected:
                                sel_id = sel["item"]["item_id"]
                                sel_vec = cand_vectors.get(sel_id)
                                if sel_vec:
                                    sim = self._cosine_sim(cand_vec, sel_vec)
                                    if sim > max_sim_to_selected:
                                        max_sim_to_selected = sim
                                        
                        mmr_score = diversity_lambda * cand["scores"].final_score - (1.0 - diversity_lambda) * max_sim_to_selected
                        if mmr_score > best_score:
                            best_score = mmr_score
                            best_idx = i
                    
                    best = unselected.pop(best_idx)
                    selected.append(best)
                    
            final_list = selected
        else:
            final_list = scored_candidates[:request.limit]
            
        # 6. Format Response
        recommended_items = []
        for cand in final_list:
            recommended_items.append(
                RecommendedItem(
                    item_id=cand["item"]["item_id"],
                    title=cand["item"]["title"],
                    category=cand["item"]["category"],
                    image_url=cand["item"].get("image_url"),
                    scores=cand["scores"]
                )
            )
            
        total_time = (time.time() - start_time) * 1000
        
        response = RecommendationResponse(
            request_id="will_be_set_by_router",
            user_id=request.user_id,
            recommendations=recommended_items,
            cache_hit=False,
            retrieval_latency_ms=retrieval_latency,
            total_latency_ms=total_time,
            candidate_count=len(candidates),
            generated_at=datetime.now(timezone.utc)
        )
        
        # 7. Cache Response
        if request.cache_ttl_seconds > 0:
            await self.cache_repo.set_recommendation(cache_key, response.model_dump(mode='json'), request.cache_ttl_seconds)
            logger.debug(f"Cached response for key {cache_key} with version user:{user_version} cat:{catalog_version}")
            
        return response
