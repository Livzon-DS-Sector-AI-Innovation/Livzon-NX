#!/usr/bin/env python3
"""
CDE 和 NMPA 栏目可行性测试脚本
使用 Playwright 测试 4 个栏目的可访问性
"""

import sys
import json
from datetime import datetime
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

# 导入统一浏览器启动工具
from browser import create_browser

# 测试目标
TARGETS = [
    {
        "source": "CDE",
        "column": "法规政策",
        "url": "https://www.cde.org.cn/main/policy/listpage/9f9c74c73e0f8f56a8bfbc646055026d"
    },
    {
        "source": "CDE",
        "column": "指导原则专栏",
        "url": "https://www.cde.org.cn/zdyz/index"
    },
    {
        "source": "NMPA",
        "column": "药品法规文件",
        "url": "https://www.nmpa.gov.cn/yaopin/ypfgwj/index.html"
    },
    {
        "source": "NMPA",
        "column": "药品政策解读",
        "url": "https://www.nmpa.gov.cn/yaopin/ypzhcjd/index.html"
    }
]

def test_channel(page, target):
    """测试单个栏目"""
    result = {
        "source": target["source"],
        "column": target["column"],
        "url": target["url"],
        "timestamp": datetime.now().isoformat(),
        "list_accessible": False,
        "title_extractable": False,
        "date_extractable": False,
        "detail_url_extractable": False,
        "detail_accessible": False,
        "content_extractable": False,
        "attachment_extractable": False,
        "records": [],
        "error": None
    }
    
    try:
        print(f"\n{'='*60}")
        print(f"测试: {target['source']} - {target['column']}")
        print(f"URL: {target['url']}")
        print(f"{'='*60}")
        
        # 1. 访问列表页
        print("\n[1/7] 访问列表页...")
        page.goto(target["url"], timeout=30000)
        page.wait_for_load_state("networkidle", timeout=30000)
        result["list_accessible"] = True
        print("✅ 列表页可访问")
        
        # 等待页面渲染
        page.wait_for_timeout(3000)
        
        # 2. 提取标题
        print("\n[2/7] 提取标题...")
        titles = page.query_selector_all("a[href]")
        title_texts = []
        for title in titles[:10]:
            text = title.inner_text().strip()
            if text and len(text) > 5:
                title_texts.append(text)
        
        if title_texts:
            result["title_extractable"] = True
            print(f"✅ 找到 {len(title_texts)} 个标题")
            for i, title in enumerate(title_texts[:3], 1):
                print(f"   {i}. {title[:60]}...")
        else:
            print("❌ 未找到标题")
        
        # 3. 提取发布日期
        print("\n[3/7] 提取发布日期...")
        date_selectors = [
            ".date", ".time", ".publish-date", ".pub-date",
            "span.date", "div.date", "td.date",
            "[class*='date']", "[class*='time']"
        ]
        
        dates = []
        for selector in date_selectors:
            date_elements = page.query_selector_all(selector)
            for elem in date_elements[:10]:
                text = elem.inner_text().strip()
                if text and len(text) >= 8:
                    dates.append(text)
        
        if dates:
            result["date_extractable"] = True
            print(f"✅ 找到 {len(dates)} 个日期")
            for i, date in enumerate(dates[:3], 1):
                print(f"   {i}. {date}")
        else:
            print("❌ 未找到日期")
        
        # 4. 提取详情链接
        print("\n[4/7] 提取详情链接...")
        links = page.query_selector_all("a[href]")
        detail_urls = []
        for link in links[:20]:
            href = link.get_attribute("href")
            if href and ("detail" in href or "content" in href or "info" in href):
                if href.startswith("http"):
                    detail_urls.append(href)
                elif href.startswith("/"):
                    from urllib.parse import urljoin
                    full_url = urljoin(target["url"], href)
                    detail_urls.append(full_url)
        
        if detail_urls:
            result["detail_url_extractable"] = True
            print(f"✅ 找到 {len(detail_urls)} 个详情链接")
            for i, url in enumerate(detail_urls[:3], 1):
                print(f"   {i}. {url}")
        else:
            print("❌ 未找到详情链接")
        
        # 5. 访问详情页
        if detail_urls:
            print("\n[5/7] 访问详情页...")
            detail_url = detail_urls[0]
            try:
                page.goto(detail_url, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=30000)
                result["detail_accessible"] = True
                print(f"✅ 详情页可访问: {detail_url}")
                
                # 6. 提取正文内容
                print("\n[6/7] 提取正文内容...")
                content_selectors = [
                    ".content", ".article-content", ".detail-content",
                    "#content", "#article", ".main-content",
                    "article", ".post-content"
                ]
                
                content_text = ""
                for selector in content_selectors:
                    elem = page.query_selector(selector)
                    if elem:
                        text = elem.inner_text().strip()
                        if text and len(text) > len(content_text):
                            content_text = text
                
                if not content_text:
                    body = page.query_selector("body")
                    if body:
                        content_text = body.inner_text().strip()
                
                if content_text and len(content_text) > 100:
                    result["content_extractable"] = True
                    print(f"✅ 正文内容长度: {len(content_text)} 字符")
                    print(f"   预览: {content_text[:100]}...")
                else:
                    print("❌ 未找到正文内容")
                
                # 7. 提取附件链接
                print("\n[7/7] 提取附件链接...")
                attachment_selectors = [
                    "a[href$='.pdf']", "a[href$='.doc']", "a[href$='.docx']",
                    "a[href*='download']", "a[href*='attachment']",
                    ".attachment a", ".download a"
                ]
                
                attachments = []
                for selector in attachment_selectors:
                    attach_elems = page.query_selector_all(selector)
                    for elem in attach_elems:
                        href = elem.get_attribute("href")
                        if href:
                            if href.startswith("http"):
                                attachments.append(href)
                            elif href.startswith("/"):
                                from urllib.parse import urljoin
                                full_url = urljoin(detail_url, href)
                                attachments.append(full_url)
                
                if attachments:
                    result["attachment_extractable"] = True
                    print(f"✅ 找到 {len(attachments)} 个附件")
                    for i, attach in enumerate(attachments[:3], 1):
                        print(f"   {i}. {attach}")
                else:
                    print("❌ 未找到附件")
                
            except Exception as e:
                print(f"❌ 详情页访问失败: {e}")
                result["error"] = str(e)
        
        # 构建样本记录
        if title_texts and detail_urls:
            for i in range(min(3, len(title_texts), len(detail_urls))):
                result["records"].append({
                    "title": title_texts[i] if i < len(title_texts) else None,
                    "detail_url": detail_urls[i] if i < len(detail_urls) else None
                })
        
    except PlaywrightTimeoutError as e:
        result["error"] = f"Timeout: {e}"
        print(f"\n❌ 超时错误: {e}")
    except Exception as e:
        result["error"] = str(e)
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    return result

def main():
    """主函数"""
    print("="*60)
    print("CDE 和 NMPA 栏目可行性测试")
    print("="*60)
    print(f"测试时间: {datetime.now().isoformat()}")
    
    results = []
    
    try:
        print("\n启动浏览器...")
        pw, browser = create_browser()
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        print("✅ 浏览器启动成功")
        
        # 测试每个栏目
        for target in TARGETS:
            result = test_channel(page, target)
            results.append(result)
        
        context.close()
        browser.close()
        pw.stop()
        print("\n✅ 浏览器已关闭")
        
    except Exception as e:
        print(f"\n❌ 浏览器启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 保存结果
    output_file = "/home/chenyingying/dazah/dazah-backend/scripts/regulatory_poc/cde_nmpa_test_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print("测试结果汇总")
    print(f"{'='*60}")
    
    for result in results:
        print(f"\n{result['source']} - {result['column']}")
        print(f"  列表页: {'✅' if result['list_accessible'] else '❌'}")
        print(f"  标题: {'✅' if result['title_extractable'] else '❌'}")
        print(f"  日期: {'✅' if result['date_extractable'] else '❌'}")
        print(f"  详情链接: {'✅' if result['detail_url_extractable'] else '❌'}")
        print(f"  详情页: {'✅' if result['detail_accessible'] else '❌'}")
        print(f"  正文: {'✅' if result['content_extractable'] else '❌'}")
        print(f"  附件: {'✅' if result['attachment_extractable'] else '❌'}")
        if result['error']:
            print(f"  错误: {result['error']}")
    
    print(f"\n✅ 结果已保存到: {output_file}")

if __name__ == "__main__":
    main()
