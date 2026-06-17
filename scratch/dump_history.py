import asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.database import async_session
from app.models import EmergencyCall
from app.schemas.emergency import EmergencyCallBrief

async def main():
    async with async_session() as db:
        result = await db.execute(
            select(EmergencyCall)
            .options(
                selectinload(EmergencyCall.user),
                selectinload(EmergencyCall.security_company),
                selectinload(EmergencyCall.guard)
            )
            .where(EmergencyCall.id == 4)
        )
        call = result.scalar_one_or_none()
        if call:
            brief = EmergencyCallBrief.model_validate(call)
            print(brief.model_dump_json(indent=2))
        else:
            print("Call 4 not found")

if __name__ == '__main__':
    asyncio.run(main())
