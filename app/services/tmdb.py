import httpx
import logging
from typing import List, Dict, Any
from app.core.settings import settings
from app.schemas.item import ItemCreate
from datetime import datetime, timezone

logger = logging.getLogger("app")

class TMDBService:
    def __init__(self):
        self.api_key = settings.TMDB_API_KEY
        self.base_url = "https://api.themoviedb.org/3"
        self.image_base_url = "https://image.tmdb.org/t/p/w500"
        
        # Mapping TMDB genre IDs to strings
        self.genre_map = {
            28: "Action",
            12: "Adventure",
            16: "Animation",
            35: "Comedy",
            80: "Crime",
            99: "Documentary",
            18: "Drama",
            10751: "Family",
            14: "Fantasy",
            36: "History",
            27: "Horror",
            10402: "Music",
            9648: "Mystery",
            10749: "Romance",
            878: "Science Fiction",
            10770: "TV Movie",
            53: "Thriller",
            10752: "War",
            37: "Western"
        }

    async def fetch_popular_movies(self, pages: int = 8) -> List[ItemCreate]:
        """Fetch popular movies from TMDB."""
        if not self.api_key:
            logger.warning("TMDB_API_KEY is not set. Cannot fetch real movies.")
            raise ValueError("TMDB_API_KEY is required for daily sync")

        items = []
        async with httpx.AsyncClient() as client:
            for page in range(1, pages + 1):
                try:
                    response = await client.get(
                        f"{self.base_url}/movie/popular",
                        params={
                            "api_key": self.api_key,
                            "language": "en-US",
                            "page": page
                        },
                        timeout=10.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    for movie in data.get("results", []):
                        if not movie.get("poster_path") or not movie.get("overview"):
                            continue # Skip movies without a poster or description
                            
                        genre_names = [self.genre_map.get(gid) for gid in movie.get("genre_ids", []) if gid in self.genre_map]
                        primary_category = genre_names[0] if genre_names else "General"
                        
                        item = ItemCreate(
                            id=f"tmdb_{movie['id']}",
                            title=movie.get("title"),
                            description=movie.get("overview"),
                            category=primary_category,
                            tags=genre_names,
                            image_url=f"{self.image_base_url}{movie['poster_path']}",
                            price=0.0,
                            popularity_score=movie.get("popularity", 0.0),
                            created_at=datetime.now(timezone.utc),
                            is_active=True
                        )
                        items.append(item)
                except Exception as e:
                    logger.error(f"Failed to fetch TMDB page {page}: {e}")
                    
        return items
