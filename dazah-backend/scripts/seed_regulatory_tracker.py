"""Seed script for regulatory tracker initial data."""

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

# Import identity models first to resolve FK references
from app.platform.identity.models import User  # noqa: F401
from app.core.database import async_session_factory
from app.modules.regulatory_tracker.models import DataChannel, DataSource


async def seed_regulatory_tracker():
    """Seed initial data for regulatory tracker."""
    
    async with async_session_factory() as session:
        # Check if already seeded
        result = await session.execute(
            select(DataSource).where(DataSource.code == "CDE")
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            print("⚠️  CDE data source already exists, skipping seed")
            return
        
        # Create CDE data source
        cde_source = DataSource(
            id=uuid.uuid4(),
            code="CDE",
            name="国家药品监督管理局药品审评中心",
            base_url="https://www.cde.org.cn",
            enabled=True,
        )
        session.add(cde_source)
        await session.flush()
        
        print(f"✅ Created data source: CDE (id={cde_source.id})")
        
        # Create CDE domestic guideline channel
        cde_guideline_channel = DataChannel(
            id=uuid.uuid4(),
            source_id=cde_source.id,
            code="cde_domestic_guideline",
            name="国内药品技术指导原则",
            list_url="https://www.cde.org.cn/zdyz/listpage/9cd8db3b7530c6fa0c86485e563f93c7",
            adapter_name="CdeDomesticGuidelineAdapter",
            enabled=True,
        )
        session.add(cde_guideline_channel)
        
        print(f"✅ Created data channel: cde_domestic_guideline (id={cde_guideline_channel.id})")
        
        await session.commit()
        print("\n✅ Seed completed successfully")
        print(f"   Data Source ID: {cde_source.id}")
        print(f"   Channel ID: {cde_guideline_channel.id}")


if __name__ == "__main__":
    asyncio.run(seed_regulatory_tracker())
