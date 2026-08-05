import hashlib
import numpy as np
from typing import List
from abc import ABC, abstractmethod
from openai import AsyncOpenAI
from app.core.settings import settings
import logging

logger = logging.getLogger("app")

class EmbeddingService(ABC):
    @abstractmethod
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        pass
        
    @property
    def dimensions(self) -> int:
        return settings.EMBEDDING_DIMENSIONS

class OpenAIEmbeddingService(EmbeddingService):
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.OPENAI_TIMEOUT_SECONDS
        )
        self.model = settings.OPENAI_EMBEDDING_MODEL

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
            
        try:
            response = await self.client.embeddings.create(
                input=texts,
                model=self.model,
                dimensions=settings.EMBEDDING_DIMENSIONS if "v3" in self.model or "3" in self.model else None
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            if "insufficient_quota" in str(e) or "429" in str(e):
                logger.warning(f"OpenAI quota exceeded. Falling back to Demo embeddings: {e}")
                demo_service = DemoEmbeddingService()
                return await demo_service.get_embeddings(texts)
                
            logger.error(f"OpenAI embedding failed: {e}")
            raise


class DemoEmbeddingService(EmbeddingService):
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        # Generate pseudo-semantic embeddings using Random Indexing / Bag-of-Words
        embeddings = []
        dim = self.dimensions
        
        for text in texts:
            # Clean and split text into words
            words = ''.join(c if c.isalnum() else ' ' for c in text.lower()).split()
            
            vec = np.zeros(dim)
            valid_words = 0
            
            for word in set(words):
                if len(word) < 3: 
                    continue # Skip very short words like 'a', 'to'
                
                # Seed a random generator with the SHA-256 digest of the word
                hasher = hashlib.sha256(word.encode("utf-8"))
                seed = int.from_bytes(hasher.digest()[:4], "little")
                
                rng = np.random.default_rng(seed)
                word_vec = rng.normal(0, 1, dim)
                vec += word_vec
                valid_words += 1
                
            # If text had no valid words, generate a random vector based on the whole text
            if valid_words == 0:
                hasher = hashlib.sha256(text.encode("utf-8"))
                seed = int.from_bytes(hasher.digest()[:4], "little")
                rng = np.random.default_rng(seed)
                vec = rng.normal(0, 1, dim)
                
            # Normalize to unit length for cosine similarity
            norm = np.linalg.norm(vec)
            if norm == 0:
                norm = 1.0
            vec = vec / norm
            embeddings.append(vec.tolist())
            
        return embeddings
