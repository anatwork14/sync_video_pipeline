import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    # Use localhost:5435 (mapped port)
    url = "postgresql+asyncpg://postgres:password@localhost:5435/videosync"
    print(f"Connecting to {url}...")
    try:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            # Check for sessions table
            res = await conn.execute(text("SELECT count(*) FROM sessions"))
            count = res.scalar()
            print(f"Success! Found {count} sessions.")
            
            # Check columns
            res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'sessions'"))
            cols = [r[0] for r in res.all()]
            print(f"Columns in sessions: {cols}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check())
