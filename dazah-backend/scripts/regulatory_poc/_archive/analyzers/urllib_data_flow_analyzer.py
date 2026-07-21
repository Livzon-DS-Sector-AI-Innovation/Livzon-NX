#!/usr/bin/env python3
"""
HTTP 数据链路分析工具（使用标准库）
分析 API 接口和数据获取链路
"""

import sys
import json
import os
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urljoin
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.request import HTTPCookieProcessor, build_opener
from http.cookiejar import CookieJar
import http.cookiejar as cookiejar
from html.parser import HTMLParser


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


class SimpleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = None
        self.scripts = []
        self.links = []
        self.in_title = False
        self.current_script = None
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "script":
            if "src" in attrs_dict:
                self.scripts.append({"src": attrs_dict["src"], "content": ""})
            else:
                self.current_script = {"src": None, "content": ""}
        elif tag == "a" and "href" in attrs_dict:
            self.links.append(attrs_dict["href"])
    
    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "script" and self.current_script:
            self.scripts.append(self.current_script)
            self.current_script = None
    
    def handle_data(self, data):
        if self.in_title:
            self.title = data
        elif self.current_script is not None:
            self.current_script["content"] += data


class UrllibDataFlowAnalyzer:
    def __init__(self):
        self.cookie_jar = CookieJar()
        self.cookie_processor = HTTPCookieProcessor(self.cookie_jar)
        
    def fetch_url(self, url, timeout=30):
        """Fetch URL with cookies"""
        opener = build_opener(self.cookie_processor)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        req = Request(url, headers=headers)
        try:
            response = opener.open(req, timeout=timeout)
            content = response.read().decode("utf-8", errors="ignore")
            return {
                "status": response.status,
                "headers": dict(response.headers),
                "content": content,
                "url": response.url,
            }
        except HTTPError as e:
            return {
                "status": e.code,
                "headers": dict(e.headers) if e.headers else {},
                "content": "",
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": None,
                "headers": {},
                "content": "",
                "error": str(e),
            }

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
            response = self.fetch_url(target["url"])
            result["page_loaded"] = response["status"] == 200
            result["response_status"] = response["status"]
            print(f"   状态码: {response['status']}")
            print(f"   Content-Type: {response['headers'].get('Content-Type', 'N/A')}")

            if not result["page_loaded"]:
                print(f"   ❌ 页面加载失败: {response.get('error', 'Unknown error')}")
                result["key_findings"].append(f"页面加载失败: {response.get('error')}")
                return result

            # Capture cookies
            cookies = [{"name": c.name, "value": c.value[:50] + "..." if len(c.value) > 50 else c.value, "domain": c.domain} 
                      for c in self.cookie_jar]
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
            parser = SimpleHTMLParser()
            parser.feed(response["content"])
            result["page_title"] = parser.title
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
                matches = re.findall(pattern, response["content"])
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
                    test_resp = self.fetch_url(test_url, timeout=10)
                    if test_resp["status"] == 200:
                        content_type = test_resp["headers"].get("Content-Type", "")
                        if "json" in content_type or "application/json" in content_type:
                            print(f"   ✅ JSON API: {test_url}")
                            try:
                                json_data = json.loads(test_resp["content"])
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
            
            # Check for Vue/React markers in HTML
            if "data-v-" in response["content"] or "__VUE__" in response["content"]:
                print(f"   检测到 Vue.js 标记")
                result["browser_required"] = True
                result["browser_required_reason"].append("Vue.js 应用，需要浏览器渲染")
            
            if 'id="root"' in response["content"] or 'id="app"' in response["content"] or "__REACT" in response["content"]:
                print(f"   检测到 React 标记")
                result["browser_required"] = True
                result["browser_required_reason"].append("React 应用，需要浏览器渲染")

            # Check for inline data
            if "window.__INITIAL_STATE__" in response["content"] or "window.__DATA__" in response["content"]:
                print(f"   ✅ 发现内联数据")
                result["key_findings"].append("页面包含内联初始化数据")

            # Step 5: Check for pagination elements
            print("\n[5] 检查分页元素...")
            pagination_patterns = [
                r'class="[^"]*pagination[^"]*"',
                r'class="[^"]*pager[^"]*"',
                r'class="[^"]*paging[^"]*"',
                r'class="[^"]*pageNav[^"]*"',
                r'href="[^"]*page=\d+[^"]*"',
            ]
            
            for pattern in pagination_patterns:
                if re.search(pattern, response["content"]):
                    print(f"   ✅ 找到分页元素")
                    result["pagination_detected"] = True
                    break

            # Step 6: Analyze scripts for API calls
            print("\n[6] 分析 JavaScript 中的 API 调用...")
            for script in parser.scripts:
                if script.get("src"):
                    # External script - try to fetch
                    script_url = urljoin(target["url"], script["src"])
                    try:
                        script_resp = self.fetch_url(script_url, timeout=10)
                        if script_resp["status"] == 200:
                            # Look for API calls
                            for pattern in api_patterns:
                                matches = re.findall(pattern, script_resp["content"])
                                for match in matches[:3]:
                                    if "/api/" in match or "listpage" in match:
                                        full_url = urljoin(script_url, match) if match.startswith("/") else match
                                        if full_url not in [a["url"] for a in result["api_endpoints_found"]]:
                                            result["api_endpoints_found"].append({
                                                "url": full_url,
                                                "source": "external_script",
                                            })
                    except:
                        pass
                elif script.get("content"):
                    # Inline script
                    for pattern in api_patterns:
                        matches = re.findall(pattern, script["content"])
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
            if re.search(r'<meta[^>]*name=["\']token["\']', response["content"], re.I):
                result["token_dependency"] = True
                result["token_details"].append("Meta token tag found")
                print(f"   ⚠️ 检测到 Token meta 标签")

            # Check response headers for tokens
            for header in ["X-Token", "X-CSRF-Token", "X-XSRF-Token"]:
                if header in response["headers"]:
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
    output_dir = "/tmp/urllib_data_flow_analysis"
    os.makedirs(output_dir, exist_ok=True)

    all_results = []

    # Allow filtering by source
    filter_source = sys.argv[1] if len(sys.argv) > 1 else None

    targets = TARGETS
    if filter_source:
        targets = [t for t in TARGETS if t["source"].upper() == filter_source.upper()]

    print("=" * 70)
    print("HTTP 数据链路分析工具（标准库版）")
    print(f"分析目标: {len(targets)} 个栏目")
    print("=" * 70)

    analyzer = UrllibDataFlowAnalyzer()

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
