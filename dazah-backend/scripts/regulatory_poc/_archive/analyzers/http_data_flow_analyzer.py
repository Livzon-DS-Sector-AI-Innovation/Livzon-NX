#!/usr/bin/env python3
"""
HTTP 数据链路分析工具
使用 requests 直接分析 API 接口
"""

import sys
import json
import os
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urljoin
import requests
from bs4 import BeautifulSoup


# 目标栏目配置
TARGETS = [
    {
        "source": "CDE",
        "section": "指导原则",
        "url": "https://www.cde.org.cn/zdyz/index",
    },
    {
        "source": "CDE",
        "section": "征求意见稿",
        "url": "https://www.cde.org.cn/main/xxgk/listpage/9f9c74c73e0f8f56a8bfbc646055026d",
    },
    {
        "source": "NMPA",
        "section": "药品法规文件",
        "url": "https://www.nmpa.gov.cn/yaopin/ypfgwj/index.html",
    },
    {
        "source": "NMPA",
        "section": "药品公告通告",
        "url": "https://www.nmpa.gov.cn/yaopin/ypgggg/index.html",
    },
    {
        "source": "NMPA",
        "section": "药品政策解读",
        "url": "https://www.nmpa.gov.cn/yaopin/ypzhcjd/index.html",
    },
]


class HTTPDataFlowAnalyzer:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        self.api_calls = []

    def analyze_page(self, target):
        """Analyze a single page's data flow"""
        print(f"\n{'='*70}")
        print(f"[{target['source']}] {target['section']}")
        print(f"URL: {target['url']}")
        print(f"{'='*70}")

        result = {
            "source": target["source"],
            "section": target["section"],
            "url": target["url"],
            "timestamp": datetime.now().isoformat(),
            "page_loaded": False,
            "page_title": None,
            "response_status": None,
            "cookies_set": [],
            "api_endpoints_found": [],
            "json_apis": [],
            "pagination_detected": False,
            "pagination_details": None,
            "token_dependency": False,
            "token_details": [],
            "anti_bot_detected": False,
            "anti_bot_details": [],
            "browser_required": False,
            "browser_required_reason": [],
            "key_findings": [],
        }

        try:
            # Step 1: Load main page
            print("\n[1] 加载页面...")
            response = self.session.get(target["url"], timeout=30)
            result["page_loaded"] = response.status_code == 200
            result["response_status"] = response.status_code
            print(f"   状态码: {response.status_code}")
            print(f"   Content-Type: {response.headers.get('content-type', 'N/A')}")

            # Capture cookies
            cookies = [{"name": c.name, "value": c.value[:50] + "...", "domain": c.domain} 
                      for c in self.session.cookies]
            result["cookies_set"] = cookies
            print(f"   Cookies: {len(cookies)} 个")
            for c in cookies[:5]:
                print(f"      - {c['name']} @ {c['domain']}")

            # Check for anti-bot cookies
            rs_cookies = [c for c in cookies if any(x in c["name"].lower() 
                         for x in ["rs", "__rs", "fasd", "fasc", "temp", "dyna", "cma_", "cmac"])]
            if rs_cookies:
                result["anti_bot_detected"] = True
                result["anti_bot_details"].append(f"反爬Cookie: {[c['name'] for c in rs_cookies]}")
                print(f"   ⚠️ 检测到反爬Cookie: {[c['name'] for c in rs_cookies]}")

            # Parse HTML
            soup = BeautifulSoup(response.text, "html.parser")
            result["page_title"] = soup.title.string if soup.title else None
            print(f"   标题: {result['page_title']}")

            # Step 2: Extract API endpoints from HTML/JS
            print("\n[2] 提取 API 端点...")
            api_patterns = [
                r'["\'](/api/[^"\']+)["\']',
                r'["\'](/main/[^"\']+listpage[^"\']*)["\']',
                r'["\']([^"\']*\/listpage\/[^"\']+)["\']',
                r'fetch\(["\']([^"\']+)["\']',
                r'axios\.[a-z]+\(["\']([^"\']+)["\']',
                r'\$\.ajax\([^)]*url:\s*["\']([^"\']+)["\']',
                r'url:\s*["\']([^"\']+api[^"\']*)["\']',
                r'["\']([^"\']*\.json[^"\']*)["\']',
            ]

            found_urls = set()
            for pattern in api_patterns:
                matches = re.findall(pattern, response.text)
                for match in matches:
                    if match.startswith("/"):
                        full_url = urljoin(target["url"], match)
                    else:
                        full_url = match
                    found_urls.add(full_url)

            print(f"   找到 {len(found_urls)} 个潜在 API 端点")
            for url in list(found_urls)[:10]:
                print(f"      → {url[:120]}")

            # Step 3: Check for common API patterns
            print("\n[3] 探测常见 API 模式...")
            base_url = target["url"].rsplit("/", 1)[0]
            common_patterns = [
                "/api/list",
                "/api/data",
                "/list",
                "/data",
                "?page=1&pageSize=20",
                "/getList",
                "/query",
            ]

            for pattern in common_patterns:
                test_url = base_url + pattern if not pattern.startswith("?") else target["url"] + pattern
                try:
                    test_resp = self.session.get(test_url, timeout=10, allow_redirects=False)
                    if test_resp.status_code == 200:
                        content_type = test_resp.headers.get("content-type", "")
                        if "json" in content_type or "application/json" in content_type:
                            print(f"   ✅ JSON API: {test_url}")
                            try:
                                json_data = test_resp.json()
                                api_info = {
                                    "url": test_url,
                                    "method": "GET",
                                    "status": 200,
                                    "is_json": True,
                                    "json_keys": list(json_data.keys()) if isinstance(json_data, dict) else f"list[{len(json_data)}]",
                                }
                                # Check for pagination
                                if isinstance(json_data, dict):
                                    for key in ["total", "records", "data", "list", "rows", "page", "pageSize"]:
                                        if key in json_data:
                                            api_info[f"has_{key}"] = True
                                            result["pagination_detected"] = True
                                result["json_apis"].append(api_info)
                            except:
                                pass
                except Exception as e:
                    pass

            # Step 4: Analyze page structure for data loading
            print("\n[4] 分析页面数据结构...")
            
            # Check for Vue/React data
            vue_data = soup.find_all(attrs={"data-v-": True})
            react_root = soup.find(id="root") or soup.find(id="app")
            
            if vue_data:
                print(f"   检测到 Vue 组件: {len(vue_data)} 个")
                result["browser_required"] = True
                result["browser_required_reason"].append("Vue.js 应用，需要浏览器渲染")
            
            if react_root:
                print(f"   检测到 React 根节点")
                result["browser_required"] = True
                result["browser_required_reason"].append("React 应用，需要浏览器渲染")

            # Check for inline data
            scripts = soup.find_all("script")
            for script in scripts:
                if script.string:
                    # Look for data initialization
                    if "window.__INITIAL_STATE__" in script.string or "window.__DATA__" in script.string:
                        print(f"   ✅ 发现内联数据")
                        result["key_findings"].append("页面包含内联初始化数据")

            # Step 5: Check for pagination elements
            print("\n[5] 检查分页元素...")
            pagination_selectors = [
                ".pagination",
                ".pager",
                "[class*='paging']",
                "[class*='pageNav']",
                "a[href*='page=']",
            ]
            
            for selector in pagination_selectors:
                if soup.select_one(selector):
                    print(f"   ✅ 找到分页元素: {selector}")
                    result["pagination_detected"] = True
                    break

            # Step 6: Try to find API in script tags
            print("\n[6] 分析 JavaScript 中的 API 调用...")
            for script in scripts:
                if script.get("src"):
                    # External script
                    script_url = urljoin(target["url"], script["src"])
                    try:
                        script_resp = self.session.get(script_url, timeout=10)
                        if script_resp.status_code == 200:
                            # Look for API calls
                            for pattern in api_patterns:
                                matches = re.findall(pattern, script_resp.text)
                                for match in matches[:3]:  # Limit to first 3
                                    if "/api/" in match or "listpage" in match:
                                        full_url = urljoin(script_url, match) if match.startswith("/") else match
                                        if full_url not in [a["url"] for a in result["api_endpoints_found"]]:
                                            result["api_endpoints_found"].append({
                                                "url": full_url,
                                                "source": "external_script",
                                            })
                    except:
                        pass
                elif script.string:
                    # Inline script
                    for pattern in api_patterns:
                        matches = re.findall(pattern, script.string)
                        for match in matches[:3]:
                            if "/api/" in match or "listpage" in match:
                                full_url = urljoin(target["url"], match) if match.startswith("/") else match
                                if full_url not in [a["url"] for a in result["api_endpoints_found"]]:
                                    result["api_endpoints_found"].append({
                                        "url": full_url,
                                        "source": "inline_script",
                                    })

            if result["api_endpoints_found"]:
                print(f"   找到 {len(result['api_endpoints_found'])} 个 API 端点:")
                for api in result["api_endpoints_found"][:5]:
                    print(f"      → {api['url'][:100]} ({api['source']})")

            # Step 7: Check for token requirements
            print("\n[7] 检查 Token 要求...")
            meta_tokens = soup.find_all("meta", attrs={"name": re.compile(r"token|csrf", re.I)})
            if meta_tokens:
                result["token_dependency"] = True
                result["token_details"].append(f"Meta tokens: {[m.get('name') for m in meta_tokens]}")
                print(f"   ⚠️ 检测到 Token meta 标签")

            # Check response headers for tokens
            for header in ["X-Token", "X-CSRF-Token", "X-XSRF-Token"]:
                if header in response.headers:
                    result["token_dependency"] = True
                    result["token_details"].append(f"Header: {header}")
                    print(f"   ⚠️ 响应头包含: {header}")

            # Step 8: Summary
            print(f"\n[8] 关键发现:")
            if result["json_apis"]:
                result["key_findings"].append(f"发现 {len(result['json_apis'])} 个 JSON API")
                print(f"   ✅ 发现 {len(result['json_apis'])} 个 JSON API")
            else:
                result["key_findings"].append("未发现直接的 JSON API")
                print(f"   ❌ 未发现直接的 JSON API")

            if result["api_endpoints_found"]:
                result["key_findings"].append(f"发现 {len(result['api_endpoints_found'])} 个 API 端点")
                print(f"   ✅ 发现 {len(result['api_endpoints_found'])} 个 API 端点")

            if result["pagination_detected"]:
                result["key_findings"].append("检测到分页机制")
                print(f"   ✅ 检测到分页机制")

            if result["anti_bot_detected"]:
                result["key_findings"].append("检测到反爬机制")
                print(f"   ⚠️ 检测到反爬机制")

            if result["browser_required"]:
                print(f"   ⚠️ 需要浏览器: {'; '.join(result['browser_required_reason'])}")
            else:
                print(f"   ✅ 可能不需要浏览器")

        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            result["error"] = str(e)

        return result


def main():
    output_dir = "/tmp/http_data_flow_analysis"
    os.makedirs(output_dir, exist_ok=True)

    all_results = []

    # Allow filtering by source
    filter_source = sys.argv[1] if len(sys.argv) > 1 else None

    targets = TARGETS
    if filter_source:
        targets = [t for t in TARGETS if t["source"].upper() == filter_source.upper()]

    print("=" * 70)
    print("HTTP 数据链路分析工具")
    print(f"分析目标: {len(targets)} 个栏目")
    print("=" * 70)

    analyzer = HTTPDataFlowAnalyzer()

    for target in targets:
        result = analyzer.analyze_page(target)
        all_results.append(result)

        # Save individual result
        filename = f"{target['source']}_{target['section']}.json"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n💾 已保存: {filepath}")

    # Save combined results
    combined_path = os.path.join(output_dir, "all_results.json")
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    # Print summary
    print(f"\n\n{'='*70}")
    print("汇总报告")
    print(f"{'='*70}")

    for r in all_results:
        print(f"\n[{r['source']}] {r['section']}")
        print(f"  页面加载: {'✅' if r['page_loaded'] else '❌'} (状态码: {r['response_status']})")
        print(f"  Cookies: {len(r['cookies_set'])} 个")
        print(f"  JSON API: {len(r['json_apis'])}")
        print(f"  API 端点: {len(r['api_endpoints_found'])}")
        print(f"  分页: {'✅' if r['pagination_detected'] else '❌'}")
        print(f"  Token依赖: {'⚠️' if r['token_dependency'] else '✅ 无'}")
        print(f"  浏览器必需: {'⚠️' if r['browser_required'] else '✅ 可能不需要'}")
        print(f"  反爬检测: {'⚠️' if r['anti_bot_detected'] else '✅ 未检测到'}")
        if r.get("error"):
            print(f"  错误: {r['error']}")

    print(f"\n✅ 所有结果已保存: {combined_path}")


if __name__ == "__main__":
    main()
