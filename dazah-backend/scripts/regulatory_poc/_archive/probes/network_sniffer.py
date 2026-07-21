#!/usr/bin/env python3
"""
网络请求嗅探工具 v2
捕获页面加载过程中的所有网络请求，包括 XHR/Fetch/JS/CSS 等
"""

import sys
import json
import os
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from browser import create_browser


class NetworkSniffer:
    def __init__(self):
        self.all_requests = []
        self.api_calls = []
        self.js_files = []
        self.html_content = ""

    def on_request(self, request):
        url = request.url
        resource_type = request.resource_type
        method = request.method

        entry = {
            "url": url,
            "method": method,
            "type": resource_type,
            "post_data": request.post_data,
            "timestamp": datetime.now().isoformat(),
        }
        self.all_requests.append(entry)

        # 分类记录
        if resource_type in ("xhr", "fetch"):
            self.api_calls.append(entry)
            print(f"  [API]  {method} {url[:120]}")
        elif resource_type == "script":
            self.js_files.append(url)
        elif resource_type == "document":
            print(f"  [DOC]  {method} {url[:120]}")

    def on_response(self, response):
        url = response.url
        request = response.request
        resource_type = request.resource_type

        # 更新对应请求的状态
        for entry in self.all_requests:
            if entry["url"] == url and entry.get("status") is None:
                entry["status"] = response.status
                entry["content_type"] = response.headers.get("content-type", "")
                break

        # 尝试读取 API 响应体
        if resource_type in ("xhr", "fetch"):
            try:
                body = response.text()
                if body:
                    for entry in self.api_calls:
                        if entry["url"] == url and "response_body" not in entry:
                            entry["response_body"] = body[:5000]
                            # 尝试解析 JSON
                            try:
                                jd = json.loads(body)
                                entry["is_json"] = True
                                entry["json_keys"] = list(jd.keys()) if isinstance(jd, dict) else f"list[{len(jd)}]"
                                # 提取分页信息
                                if isinstance(jd, dict):
                                    for k in ("total", "totalCount", "total_count", "count", "records", "data", "rows", "list", "result"):
                                        if k in jd:
                                            v = jd[k]
                                            if isinstance(v, list):
                                                entry[f"json_{k}_len"] = len(v)
                                                if v:
                                                    entry[f"json_{k}_sample_keys"] = list(v[0].keys()) if isinstance(v[0], dict) else type(v[0]).__name__
                                            else:
                                                entry[f"json_{k}"] = v
                            except json.JSONDecodeError:
                                entry["is_json"] = False
            except Exception:
                pass

    def analyze(self, url, output_dir="/tmp"):
        print(f"\n{'='*70}")
        print(f"分析: {url}")
        print(f"{'='*70}")

        self.all_requests = []
        self.api_calls = []
        self.js_files = []

        pw, browser = create_browser()
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        # 绑定事件
        page.on("request", self.on_request)
        page.on("response", self.on_response)

        try:
            print("\n[1] 加载页面...")
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            print("[2] 等待 networkidle...")
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                print("   (networkidle 超时，继续)")

            page.wait_for_timeout(3000)

            # 保存 HTML
            self.html_content = page.content()
            domain = urlparse(url).netloc.replace(".", "_")
            html_path = os.path.join(output_dir, f"{domain}_page.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(self.html_content)
            print(f"   HTML 已保存: {html_path} ({len(self.html_content)} 字符)")

            # 分析 HTML 中的列表结构
            print("\n[3] 页面结构分析:")
            print(f"   标题: {page.title()}")

            links = page.query_selector_all("a[href]")
            print(f"   链接总数: {len(links)}")

            # 提取有意义的链接
            meaningful_links = []
            for link in links:
                text = link.inner_text().strip()
                href = link.get_attribute("href") or ""
                if text and len(text) > 8 and href and not href.startswith("javascript:"):
                    meaningful_links.append({"text": text[:80], "href": href[:150]})

            print(f"   有效链接: {len(meaningful_links)}")
            if meaningful_links:
                print("   前 5 个:")
                for i, ml in enumerate(meaningful_links[:5], 1):
                    print(f"     {i}. {ml['text']}")
                    print(f"        {ml['href']}")

            # 检查分页
            print("\n[4] 分页元素:")
            page_el = page.query_selector(".pagination, .pager, .page-bar, [class*='paging'], [class*='pageNav']")
            if page_el:
                print(f"   找到分页: {page_el.inner_text().strip()[:100]}")
            else:
                print("   未找到分页元素")

            # 检查是否有 Vue/React 标记
            print("\n[5] 前端框架检测:")
            has_vue = page.evaluate("() => !!window.__VUE__ || !!window.Vue")
            has_react = page.evaluate("() => !!window.__REACT_DEVTOOLS_GLOBAL_HOOK__ || !!document.querySelector('[data-reactroot]')")
            has_angular = page.evaluate("() => !!window.ng || !!document.querySelector('[ng-app]')")
            print(f"   Vue: {'✅' if has_vue else '❌'}")
            print(f"   React: {'✅' if has_react else '❌'}")
            print(f"   Angular: {'✅' if has_angular else '❌'}")

            # 尝试触发翻页，看是否有新请求
            print("\n[6] 尝试翻页触发 API...")
            before_count = len(self.api_calls)

            # 找下一页按钮
            next_btn = page.query_selector("a.next, .pagination .next, [class*='next'], a:has-text('下一页'), button:has-text('下一页')")
            if next_btn:
                print("   找到下一页按钮，点击...")
                try:
                    next_btn.click()
                    page.wait_for_timeout(3000)
                    after_count = len(self.api_calls)
                    if after_count > before_count:
                        print(f"   ✅ 翻页后新增 {after_count - before_count} 个 API 请求!")
                    else:
                        print("   翻页后无新 API 请求")
                except Exception as e:
                    print(f"   点击失败: {e}")
            else:
                print("   未找到下一页按钮")

        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            context.close()
            browser.close()
            pw.stop()

        return {
            "url": url,
            "all_requests": self.all_requests,
            "api_calls": self.api_calls,
            "js_files": self.js_files,
            "html_length": len(self.html_content),
        }


def main():
    if len(sys.argv) < 2:
        print("用法: python network_sniffer.py <url> [output_file]")
        sys.exit(1)

    url = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else f"/tmp/sniff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    print("=" * 70)
    print("网络请求嗅探工具 v2")
    print("=" * 70)
    print(f"目标: {url}")
    print(f"输出: {output_file}")

    sniffer = NetworkSniffer()
    result = sniffer.analyze(url)

    # 保存
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*70}")
    print(f"汇总")
    print(f"{'='*70}")
    print(f"总请求数: {len(result['all_requests'])}")
    print(f"API 请求: {len(result['api_calls'])}")
    print(f"JS 文件:  {len(result['js_files'])}")
    print(f"HTML 长度: {result['html_length']}")

    if result["api_calls"]:
        print(f"\nAPI 详情:")
        for i, api in enumerate(result["api_calls"], 1):
            print(f"\n  [{i}] {api['method']} {api['url']}")
            print(f"      状态: {api.get('status', 'N/A')}")
            if api.get("post_data"):
                print(f"      POST: {api['post_data'][:200]}")
            if api.get("is_json"):
                print(f"      JSON keys: {api.get('json_keys')}")
            if api.get("response_body"):
                print(f"      响应预览: {api['response_body'][:300]}")

    print(f"\n✅ 结果已保存: {output_file}")


if __name__ == "__main__":
    main()
