import asyncio
import os
from dotenv import load_dotenv
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

load_dotenv(".env.local")

async def create_indexes():
    client = AsyncQdrantClient(
        url=os.getenv("QDRANT_URL").strip(),
        api_key=os.getenv("QDRANT_API_KEY").strip()
    )
    collection_name = os.getenv("QDRANT_COLLECTION_NAME", "items_collection").strip()
    
    print("Creating index for item_id...")
    await client.create_payload_index(collection_name, "item_id", models.PayloadSchemaType.KEYWORD)
    
    print("Creating index for category...")
    await client.create_payload_index(collection_name, "category", models.PayloadSchemaType.KEYWORD)
    
    print("Creating index for price...")
    await client.create_payload_index(collection_name, "price", models.PayloadSchemaType.FLOAT)
    
    print("Done!")

if __name__ == "__main__":
    asyncio.run(create_indexes())
