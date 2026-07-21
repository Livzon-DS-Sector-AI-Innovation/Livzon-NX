#!/usr/bin/env python3
"""
调试脚本：截图并保存页面内容
"""

import sys
from datetime import datetime

# 导入统一浏览器启动工具
from browser import create_browser

TARGETS = [
    {"source": "CDE", "column": "法规政策", "url": "https://www.cde.org.cn/main/policy/listpage/9f9c74c73e0f8f56a8bfbc646055026d"},
    {"source": "CDE", "column": "指导原则专栏", "url": "https://www.cde.org.cn/zdyz/index"},
    {"source": "NMPA", "column": "药品法规文件", "url": "https://www.nmpa.gov.cn/yaopin/ypfgwj/index.html"},
    {"source": "NMPA", "column": "药品政策解读", "url": "https://www.nmpa.gov.cn/yaopin/ypzhcjd/index.html"}
]

def debug_page(page, target, index):
    """调试单个页面"""
    print(f"\n{'='*60}")
    print(f"调试: {target['source']} - {target['column']}")
    print(f"URL: {target['url']}")
    print(f"{'='*60}")
    
    try:
        # 访问页面
        print("\n[1] 访问页面...")
        page.goto(target["url"], timeout=30000)
        page.wait_for_load_state("networkidle", timeout=30000)
        print("✅ 页面加载完成")
        
        # 等待更长时间让 JS 渲染
        print("\n[2] 等待 JavaScript 渲染 (5秒)...")
        page.wait_for_timeout(5000)
        
        # 截图
        screenshot_file = f"/tmp/debug_{index}_{target['source']}_{target['column'].replace(' ', '_')}.png"
        page.screenshot(path=screenshot_file, full_page=True)
        print(f"✅ 截图已保存: {screenshot_file}")
        
        # 保存 HTML
        html_file = f"/tmp/debug_{index}_{target['source']}_{target['column'].replace(' ', '_')}.html"
        html_content = page.content()
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"✅ HTML 已保存: {html_file}")
        
        # 分析页面结构
        print("\n[3] 分析页面结构...")
        
        # 查找所有链接
        links = page.query_selector_all("a")
        print(f"   链接总数: {len(links)}")
        
        # 查找包含文本的链接
        text_links = []
        for link in links[:50]:
            text = link.inner_text().strip()
            href = link.get_attribute("href")
            if text and len(text) > 5 and href:
                text_links.append({"text": text[:60], "href": href[:80]})
        
        print(f"   有效链接: {len(text_links)}")
        if text_links:
            print("   前5个链接:")
            for i, link in enumerate(text_links[:5], 1):
                print(f"     {i}. {link['text']}")
                print(f"        {link['href']}")
        
        # 查找日期元素
        date_selectors = [".date", ".time", "[class*='date']", "[class*='time']"]
        date_count = 0
        for selector in date_selectors:
            elems = page.query_selector_all(selector)
            date_count += len(elems)
        print(f"   日期元素: {date_count}")
        
        # 查找内容区域
        content_selectors = [".content", ".article", "#content", "article", ".main"]
        content_found = False
        for selector in content_selectors:
            elem = page.query_selector(selector)
            if elem:
                content_found = True
                text = elem.inner_text().strip()
                print(f"   内容区域 ({selector}): {len(text)} 字符")
                break
        if not content_found:
            print("   内容区域: 未找到")
        
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()

def main():
    """主函数"""
    print("="*60)
    print("页面调试工具")
    print("="*60)
    print(f"时间: {datetime.now().isoformat()}")
    print(f"目标数量: {len(TARGETS)}")
    
    try:
        print("\n启动浏览器...")
        pw, browser = create_browser()
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        print("✅ 浏览器启动成功")
        
        for i, target in enumerate(TARGETS, 1):
            debug_page(page, target, i)
        
        context.close()
        browser.close()
        pw.stop()
        print("\n✅ 调试完成")
        
    except Exception as e:
        print(f"\n❌ 浏览器启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
