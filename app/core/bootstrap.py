import logging
import os
from sqlalchemy import select
from app.core.database import async_session
from app.models import SecurityCompany, CompanyAdmin, GlobalAdmin
from app.services.admin import CompanyAdminService
from app.services.global_admin import GlobalAdminService
from app.core.config import settings

logger = logging.getLogger(__name__)

async def bootstrap_admin():
    """
    Bootstrap an initial admin user and security company based on environment variables.
    Variables:
    - BOOTSTRAP_ADMIN_EMAIL
    - BOOTSTRAP_ADMIN_PASSWORD
    - BOOTSTRAP_COMPANY_NAME
    """
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    company_name = os.getenv("BOOTSTRAP_COMPANY_NAME", "Default Security Company")

    if not email or not password:
        logger.info("Bootstrap admin not configured (BOOTSTRAP_ADMIN_EMAIL/PASSWORD missing). Skipping.")
        return

    async with async_session() as session:
        # 1. Check if company exists, create if not
        result = await session.execute(
            select(SecurityCompany).where(SecurityCompany.name == company_name)
        )
        company = result.scalar_one_or_none()

        if not company:
            logger.info(f"Bootstrapping: Creating company '{company_name}'...")
            company = SecurityCompany(
                name=company_name,
                legal_name=f"{company_name} LLP",
                email=email,
                is_active=True,
                is_accepting_calls=True
            )
            session.add(company)
            await session.flush()
            logger.info(f"Bootstrapping: Company created (ID: {company.id}).")
        else:
            logger.info(f"Bootstrapping: Company '{company_name}' already exists.")

        # 2. Check if admin exists, create if not
        admin = await CompanyAdminService.get_by_email(session, email)
        if not admin:
            logger.info(f"Bootstrapping: Creating owner admin '{email}'...")
            admin = await CompanyAdminService.create(
                session,
                security_company_id=company.id,
                email=email,
                password=password,
                full_name="Initial Admin",
                role="owner"
            )
            await session.commit()
            logger.info(f"Bootstrapping: Admin '{email}' created successfully.")
        else:
            logger.info(f"Bootstrapping: Admin '{email}' already exists.")


async def bootstrap_global_admin():
    """Bootstrap an initial global admin based on environment variables."""
    email = settings.bootstrap_global_admin_email
    password = settings.bootstrap_global_admin_password

    if not email or not password:
        logger.info("Bootstrap global admin not configured. Skipping.")
        return

    async with async_session() as session:
        admin = await GlobalAdminService.get_by_email(session, email)
        if not admin:
            logger.info(f"Bootstrapping: Creating global admin '{email}'...")
            await GlobalAdminService.create(
                session,
                email=email,
                password=password,
                full_name="System Superadmin",
                role="superadmin"
            )
            await session.commit()
            logger.info(f"Bootstrapping: Global admin '{email}' created successfully.")
        else:
            logger.info(f"Bootstrapping: Global admin '{email}' already exists.")


async def run_bootstrap():
    """Run all bootstrap tasks."""
    await bootstrap_admin()
    await bootstrap_global_admin()
