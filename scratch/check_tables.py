import asyncio
import os
from sqlalchemy import text
from app.core.database import engine

async def check_tables():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public';"))
        tables = [row[0] for row in result.fetchall()]
        print(f"Current tables: {tables}")
        if 'guard_devices' in tables:
            print("WARNING: guard_devices table still exists!")
        else:
            print("SUCCESS: guard_devices table has been removed.")

if __name__ == "__main__":
    asyncio.run(check_tables())
