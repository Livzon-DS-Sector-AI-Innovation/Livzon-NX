"""测试 S.6 AI 填充功能"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

BASE_URL = "http://localhost:8000/api/v1/dossier-writer"

# S.6 章节 ID (from existing data)
CHAPTER_ID = "7d56b3bd-3dab-4fb2-9ef8-e550d9cce864"


async def test_asset_categories():
    """测试获取素材分类"""
    print("\n=== 测试获取素材分类 ===")
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/chapters/3.2.S.6/asset-categories")
        data = resp.json()
        print(f"状态码: {resp.status_code}")
        print(f"成功: {data.get('success')}")
        print(f"分类数量: {len(data.get('data', []))}")
        for cat in data.get('data', [])[:3]:
            print(f"  - {cat['category_name']}: {cat['description'][:50]}")
        return data.get('success')


async def test_ai_preview():
    """测试 AI 解析预览"""
    print("\n=== 测试 AI 解析预览 ===")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{BASE_URL}/chapters/{CHAPTER_ID}/ai-preview")
        data = resp.json()
        print(f"状态码: {resp.status_code}")
        print(f"成功: {data.get('success')}")
        print(f"消息: {data.get('message')}")
        
        if data.get('success') and data.get('data'):
            result = data['data']
            print(f"\n提取字段数: {len(result.get('fields', []))}")
            print(f"Token 使用: {result.get('token_usage', {})}")
            
            for field in result.get('fields', [])[:5]:
                status = "✓" if field.get('value') else "✗"
                print(f"  {status} {field['field_name']}: {str(field.get('value', ''))[:50]}")
        
        return data.get('success')


async def main():
    print("=" * 60)
    print("S.6 AI 填充功能测试")
    print("=" * 60)
    
    # 测试 1: 获取素材分类
    success1 = await test_asset_categories()
    
    # 测试 2: AI 解析预览
    success2 = await test_ai_preview()
    
    print("\n" + "=" * 60)
    print("测试总结:")
    print(f"  素材分类 API: {'✓ 通过' if success1 else '✗ 失败'}")
    print(f"  AI 解析预览: {'✓ 通过' if success2 else '✗ 失败'}")
    print("=" * 60)
    
    if not success2:
        print("\n提示: 如果 AI 解析预览失败，请检查 .env 文件中的 LLM_API_KEY 是否已配置")


if __name__ == "__main__":
    asyncio.run(main())
