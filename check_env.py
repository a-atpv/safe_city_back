import os
import sys
from sqlalchemy import create_engine, select, text
from dotenv import load_dotenv

load_dotenv()

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("DATABASE_URL not found in .env")
    sys.exit(1)

# Fix for sync driver if using asyncpg in url
if "postgresql+asyncpg" in db_url:
    sync_url = db_url.replace("postgresql+asyncpg", "postgresql")
else:
    sync_url = db_url

try:
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        print("Successfully connected to the database!")
        # Check guards
        result = conn.execute(text("SELECT id, full_name, is_online, is_on_call, status, current_latitude, current_longitude FROM guards"))
        guards = result.fetchall()
        print(f"\nFound {len(guards)} guards:")
        for g in guards:
            print(f"ID: {g[0]}, Name: {g[1]}, Online: {g[2]}, On Call: {g[3]}, Status: {g[4]}, Lat: {g[5]}, Lon: {g[6]}")
        
        # Check calls
        result = conn.execute(text("SELECT id, status, guard_id, latitude, longitude FROM emergency_calls"))
        calls = result.fetchall()
        print(f"\nFound {len(calls)} calls:")
        for c in calls:
            print(f"ID: {c[0]}, Status: {c[1]}, GuardID: {c[2]}, Lat: {c[3]}, Lon: {c[4]}")
            
except Exception as e:
    print(f"Error: {e}")
