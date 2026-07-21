"""Seed script for regulatory documents initial data.

从 seed/cde_guidelines.json 导入初始法规数据。
"""

import asyncio
import json
import os
import sys
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.platform.identity.models import User  # noqa: F401
from app.core.database import async_session_factory
from app.modules.regulatory_tracker.models import DataChannel, DataSource, RegulatoryDocument


async def seed_regulatory_documents():
    """Seed initial regulatory documents from JSON file."""
    
    # 读取 JSON 文件
    json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed", "cde_guidelines.json")
    
    if not os.path.exists(json_path):
        print(f"❌ 文件不存在: {json_path}")
        return
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    source_id = data["source_id"]
    channel_id = data["channel_id"]
    documents = data["documents"]
    
    print(f"📖 准备导入 {len(documents)} 条法规数据...")
    
    async with async_session_factory() as session:
        # 验证 source 和 channel 存在
        source = await session.execute(
            select(DataSource).where(DataSource.id == source_id)
        )
        source = source.scalar_one_or_none()
        
        if not source:
            print("❌ 数据源不存在，请先执行 seed_regulatory_tracker.py")
            return
        
        channel = await session.execute(
            select(DataChannel).where(DataChannel.id == channel_id)
        )
        channel = channel.scalar_one_or_none()
        
        if not channel:
            print("❌ 数据通道不存在，请先执行 seed_regulatory_tracker.py")
            return
        
        # 检查是否已有数据
        existing_count = await session.execute(
            select(RegulatoryDocument).where(
                RegulatoryDocument.source_id == source_id,
                RegulatoryDocument.channel_id == channel_id
            )
        )
        existing_count = len(existing_count.scalars().all())
        
        if existing_count > 0:
            print(f"⚠️  已存在 {existing_count} 条法规数据，跳过导入")
            return
        
        # 导入数据
        for doc_data in documents:
            # 解析日期
            publish_date = None
            if doc_data.get("publish_date"):
                try:
                    publish_date = date.fromisoformat(doc_data["publish_date"])
                except ValueError:
                    pass
            
            doc = RegulatoryDocument(
                source_id=source_id,
                channel_id=channel_id,
                document_id=doc_data["document_id"],
                title=doc_data["title"],
                publish_date=publish_date,
                status_text=doc_data.get("status_text"),
                classification=doc_data.get("classification"),
                original_url=doc_data.get("original_url"),
                raw_data=doc_data.get("raw_data"),
                is_new=False,
                is_read=True,
                first_found_at=datetime.now() - timedelta(days=1),
                last_checked_at=datetime.now()
            )
            session.add(doc)
        
        await session.commit()
        print(f"✅ 成功导入 {len(documents)} 条法规数据")
        print(f"   - is_new = false")
        print(f"   - is_read = true")


if __name__ == "__main__":
    asyncio.run(seed_regulatory_documents())
