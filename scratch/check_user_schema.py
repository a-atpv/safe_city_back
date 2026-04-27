import asyncio
from sqlalchemy import text
from app.core import connect_db, get_db

async def check_schema():
    async for db in get_db():
        result = await db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"))
        columns = [row[0] for row in result.all()]
        print(f"Columns in users table: {columns}")
        
        result = await db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_name = 'user_devices'"))
        exists = result.scalar_one_or_none()
        print(f"user_devices table exists: {exists is not None}")
        break

if __name__ == "__main__":
    asyncio.run(check_schema())
