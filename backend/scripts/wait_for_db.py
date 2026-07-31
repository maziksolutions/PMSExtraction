import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Add parent directory to sys.path to allow imports from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

async def wait_for_db():
    print("Waiting for database to become available...")
    engine = create_async_engine(settings.async_database_url)
    
    max_retries = 30
    retry_interval = 2 # seconds
    
    for i in range(1, max_retries + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            print("Database is ready!")
            await engine.dispose()
            sys.exit(0)
        except Exception as e:
            print(f"[{i}/{max_retries}] Database connection failed: {e}. Retrying in {retry_interval}s...")
            await asyncio.sleep(retry_interval)
            
    print("Error: Database not available after all retries.")
    await engine.dispose()
    sys.exit(1)

if __name__ == "__main__":
    asyncio.run(wait_for_db())
