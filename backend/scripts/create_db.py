import asyncio

from sqlalchemy import text

from app.core.db import Base, engine
import app.models  # noqa: F401  (registers tables)
from app.models.embedding import EMBED_DIM  # noqa: F401


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS company_memory_embedding_hnsw "
                "ON company_memory USING hnsw (embedding vector_cosine_ops)"
            )
        )
    await engine.dispose()
    print("Database ready (extension + tables + vector index).")


if __name__ == "__main__":
    asyncio.run(main())
