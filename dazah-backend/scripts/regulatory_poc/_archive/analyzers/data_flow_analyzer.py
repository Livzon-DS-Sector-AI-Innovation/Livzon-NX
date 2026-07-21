#!/usr/bin/env python3
"""
数据链路分析工具
使用 Playwright 捕获真实浏览器环境下的所有 XHR/Fetch 请求
分析每个栏目的数据获取链路
"""

import sys
import json
import os
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from browser import create_browser


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


class DataFlowAnalyzer:
    def __init__(self):
        self.requests_log = []
        self.api_calls = []
        self.cookies_snapshot = []

    def _on_request(self, request):
        entry = {
            "url": request.url,
            "method": request.method,
            "type": request.resource_type,
            "post_data": request.post_data,
            "headers": dict(request.headers),
            "timestamp": datetime.now().isoformat(),
        }
        self.requests_log.append(entry)
        if request.resource_type in ("xhr", "fetch"):
            self.api_calls.append(entry)

    def _on_response(self, response):
        url = response.url
        req = response.request
        if req.resource_type not in ("xhr", "fetch"):
            return

        # Find matching api_call entry
        for entry in self.api_calls:
            if entry["url"] == url and "status" not in entry:
                entry["status"] = response.status
                entry["response_headers"] = dict(response.headers)
                entry["content_type"] = response.headers.get("content-type", "")
                break

        # Try to read response body
        try:
            body = response.text()
            if body:
                for entry in self.api_calls:
                    if entry["url"] == url and "response_body" not in entry:
                        entry["response_body"] = body[:10000]
                        entry["response_length"] = len(body)
                        # Parse JSON
                        try:
                            jd = json.loads(body)
                            entry["is_json"] = True
                            if isinstance(jd, dict):
                                entry["json_top_keys"] = list(jd.keys())[:20]
                                # Look for pagination fields
                                for key in ("total", "totalCount", "total_count", "count",
                                           "records", "data", "rows", "list", "result",
                                           "pageData", "page", "pageSize", "pageNum"):
                                    if key in jd:
                                        val = jd[key]
                                        if isinstance(val, list):
                                            entry[f"field_{key}_type"] = "list"
                                            entry[f"field_{key}_len"] = len(val)
                                            if val and isinstance(val[0], dict):
                                                entry[f"field_{key}_item_keys"] = list(val[0].keys())[:15]
                                        elif isinstance(val, (int, float)):
                                            entry[f"field_{key}_value"] = val
                                        elif isinstance(val, dict):
                                            entry[f"field_{key}_keys"] = list(val.keys())[:10]
                            elif isinstance(jd, list):
                                entry["is_json"] = True
                                entry["json_type"] = f"list[{len(jd)}]"
                                if jd and isinstance(jd[0], dict):
                                    entry["json_item_keys"] = list(jd[0].keys())[:15]
                        except (json.JSONDecodeError, ValueError):
                            entry["is_json"] = False
                        break
        except Exception:
            pass

    def analyze_page(self, target):
        """Analyze a single page's data flow"""
        print(f"\n{'='*70}")
        print(f"[{target['source']}] {target['section']}")
        print(f"URL: {target['url']}")
        print(f"{'='*70}")

        self.requests_log = []
        self.api_calls = []

        pw, browser = create_browser()
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.on("request", self._on_request)
        page.on("response", self._on_response)

        result = {
            "source": target["source"],
            "section": target["section"],
            "url": target["url"],
            "timestamp": datetime.now().isoformat(),
            "page_loaded": False,
            "page_title": None,
            "total_requests": 0,
            "xhr_fetch_count": 0,
            "json_apis": [],
            "pagination_detected": False,
            "pagination_details": None,
            "cookie_dependency": False,
            "token_dependency": False,
            "token_details": None,
            "browser_required": False,
            "browser_required_reason": [],
            "anti_bot_detected": False,
            "anti_bot_details": [],
            "all_xhr_urls": [],
            "key_findings": [],
        }

        try:
            # Step 1: Load page
            print("\n[1] 加载页面...")
            response = page.goto(target["url"], timeout=30000, wait_until="domcontentloaded")
            result["page_loaded"] = True
            result["page_title"] = page.title()
            result["initial_response_status"] = response.status if response else None
            print(f"   标题: {result['page_title']}")
            print(f"   状态码: {result['initial_response_status']}")

            # Step 2: Wait for network to settle
            print("[2] 等待 networkidle...")
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                print("   (networkidle 超时)")
            page.wait_for_timeout(3000)

            # Step 3: Capture cookies
            cookies = context.cookies()
            result["cookies_count"] = len(cookies)
            result["cookies"] = [{"name": c["name"], "domain": c["domain"]} for c in cookies]
            print(f"[3] Cookies: {len(cookies)} 个")
            for c in cookies[:10]:
                print(f"   - {c['name']} @ {c['domain']}")

            # Check for anti-bot cookies (瑞数 related)
            rs_cookies = [c for c in cookies if any(x in c["name"].lower() for x in ["rs", "__rs", "fasd", "fasc", "temp", "dyna", "cma_", "cmac"])]
            if rs_cookies:
                result["anti_bot_detected"] = True
                result["anti_bot_details"].append(f"瑞数相关Cookie: {[c['name'] for c in rs_cookies]}")
                print(f"   ⚠️ 检测到反爬Cookie: {[c['name'] for c in rs_cookies]}")

            # Step 4: Analyze XHR/Fetch requests
            result["total_requests"] = len(self.requests_log)
            result["xhr_fetch_count"] = len(self.api_calls)
            print(f"\n[4] 网络请求统计:")
            print(f"   总请求数: {result['total_requests']}")
            print(f"   XHR/Fetch: {result['xhr_fetch_count']}")

            # Categorize APIs
            json_apis = []
            html_apis = []
            js_apis = []
            other_apis = []

            for api in self.api_calls:
                result["all_xhr_urls"].append(api["url"])
                ct = api.get("content_type", "")
                if api.get("is_json"):
                    json_apis.append(api)
                elif "html" in ct:
                    html_apis.append(api)
                elif "javascript" in ct:
                    js_apis.append(api)
                else:
                    other_apis.append(api)

            print(f"\n   JSON API: {len(json_apis)}")
            print(f"   HTML API: {len(html_apis)}")
            print(f"   JS API:   {len(js_apis)}")
            print(f"   Other:    {len(other_apis)}")

            # Step 5: Analyze JSON APIs in detail
            print(f"\n[5] JSON API 详情:")
            for i, api in enumerate(json_apis, 1):
                parsed = urlparse(api["url"])
                short_url = parsed.path
                if parsed.query:
                    short_url += "?" + parsed.query[:80]
                print(f"\n   [{i}] {api['method']} {short_url}")
                print(f"       状态: {api.get('status')}")
                print(f"       Content-Type: {api.get('content_type', 'N/A')[:60]}")
                if api.get("json_top_keys"):
                    print(f"       JSON keys: {api['json_top_keys']}")
                for key in api.get("json_top_keys", []):
                    field_type = api.get(f"field_{key}_type")
                    field_val = api.get(f"field_{key}_value")
                    field_len = api.get(f"field_{key}_len")
                    if field_type == "list":
                        print(f"       📋 {key}: list[{field_len}]")
                        item_keys = api.get(f"field_{key}_item_keys")
                        if item_keys:
                            print(f"          item keys: {item_keys}")
                    elif field_val is not None:
                        print(f"       🔢 {key}: {field_val}")

                # Check for pagination indicators
                pagination_keys = {"total", "totalCount", "total_count", "count", "page", "pageSize", "pageNum", "pageData"}
                found_pagination = pagination_keys & set(api.get("json_top_keys", []))
                if found_pagination:
                    result["pagination_detected"] = True
                    result["pagination_details"] = {
                        "api_url": api["url"],
                        "pagination_keys": list(found_pagination),
                    }

                # Store cleaned API info
                json_apis_clean = {
                    "url": api["url"],
                    "method": api["method"],
                    "status": api.get("status"),
                    "post_data": api.get("post_data"),
                    "json_top_keys": api.get("json_top_keys"),
                    "content_type": api.get("content_type"),
                }
                # Add pagination fields
                for key in api.get("json_top_keys", []):
                    for prefix in ("field_",):
                        for suffix in ("_type", "_len", "_value", "_item_keys"):
                            full_key = f"{prefix}{key}{suffix}"
                            if full_key in api:
                                json_apis_clean[full_key] = api[full_key]

                # Check response body preview
                if api.get("response_body"):
                    json_apis_clean["response_preview"] = api["response_body"][:500]

                result["json_apis"].append(json_apis_clean)

            # Step 6: Check for dynamic tokens
            print(f"\n[6] Token 分析:")
            token_indicators = []

            # Check request headers for tokens
            for api in self.api_calls:
                headers = api.get("headers", {})
                for h in ("x-token", "authorization", "x-csrf-token", "x-xsrf-token"):
                    if h in headers:
                        token_indicators.append(f"Header '{h}' found in {api['url'][:80]}")

                # Check URL for token params
                qs = parse_qs(parsed.query if parsed.netloc else urlparse(api["url"]).query)
                for tk in ("token", "_token", "sign", "_sign", "ts", "_t"):
                    if tk in qs:
                        token_indicators.append(f"URL param '{tk}' in {api['url'][:80]}")

            # Check for meta tags with tokens
            try:
                meta_token = page.evaluate("""() => {
                    const metas = document.querySelectorAll('meta[name*="token"], meta[name*="csrf"]');
                    return Array.from(metas).map(m => ({name: m.name, content: m.content}));
                }""")
                if meta_token:
                    token_indicators.append(f"Meta tokens: {meta_token}")
            except Exception:
                pass

            # Check for 瑞数 dynamic JS
            try:
                rs_scripts = page.evaluate("""() => {
                    const scripts = document.querySelectorAll('script[src]');
                    return Array.from(scripts).map(s => s.src).filter(s =>
                        s.includes('/fjgs') || s.includes('/dynamic') ||
                        s.match(/\/[a-f0-9]{4,}\.js$/) || s.includes('rs_')
                    );
                }""")
                if rs_scripts:
                    result["anti_bot_detected"] = True
                    result["anti_bot_details"].append(f"疑似动态JS: {rs_scripts}")
                    token_indicators.append(f"动态脚本: {rs_scripts}")
            except Exception:
                pass

            if token_indicators:
                result["token_dependency"] = True
                result["token_details"] = token_indicators
                for t in token_indicators:
                    print(f"   ⚠️ {t}")
            else:
                print("   未检测到动态 Token")

            # Step 7: Check if browser is required
            print(f"\n[7] 浏览器必要性分析:")
            browser_required_reasons = []

            # If no JSON APIs found, data might be server-rendered
            if len(json_apis) == 0 and result["xhr_fetch_count"] == 0:
                browser_required_reasons.append("无 XHR/Fetch 请求，数据可能服务端渲染在 HTML 中")

            # If anti-bot detected
            if result["anti_bot_detected"]:
                browser_required_reasons.append(f"检测到反爬机制: {'; '.join(result['anti_bot_details'])}")

            # If tokens are dynamic
            if result["token_dependency"]:
                browser_required_reasons.append("存在动态 Token，需要浏览器环境生成")

            # Check if HTML APIs are used to load content (HTML fragments)
            if html_apis and not json_apis:
                browser_required_reasons.append("使用 HTML 片段加载，非 JSON API")

            result["browser_required"] = len(browser_required_reasons) > 0
            result["browser_required_reason"] = browser_required_reasons
            for r in browser_required_reasons:
                print(f"   → {r}")
            if not browser_required_reasons:
                print("   ✅ 可能不需要完整浏览器")

            # Step 8: Try pagination click
            print(f"\n[8] 翻页测试:")
            before_api_count = len(self.api_calls)

            # Look for pagination elements
            pagination_selectors = [
                ".pagination .next",
                "a.next",
                "[class*='next']",
                "a:has-text('下一页')",
                "button:has-text('下一页')",
                ".page-next",
                "#nextPage",
                "a:has-text('>')",
            ]

            clicked = False
            for sel in pagination_selectors:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        print(f"   找到翻页按钮: {sel}")
                        el.click()
                        page.wait_for_timeout(3000)
                        clicked = True
                        break
                except Exception:
                    continue

            if clicked:
                new_apis = len(self.api_calls) - before_api_count
                if new_apis > 0:
                    print(f"   ✅ 翻页触发 {new_apis} 个新 API 请求")
                    result["pagination_detected"] = True
                    # Capture the new API calls
                    for api in self.api_calls[before_api_count:]:
                        if api.get("is_json"):
                            result["key_findings"].append(f"翻页触发API: {api['url'][:100]}")
                            if not result.get("pagination_details"):
                                result["pagination_details"] = {
                                    "api_url": api["url"],
                                    "trigger": "click_next_page",
                                }
                else:
                    print(f"   翻页后无新 API 请求 (可能服务端渲染)")
            else:
                print(f"   未找到翻页按钮")

            # Step 9: Key findings summary
            print(f"\n[9] 关键发现:")
            if result["json_apis"]:
                result["key_findings"].append(f"发现 {len(result['json_apis'])} 个 JSON API")
                print(f"   ✅ 发现 {len(result['json_apis'])} 个 JSON API")
                for api in result["json_apis"]:
                    print(f"      → {api['method']} {api['url'][:100]}")
            else:
                result["key_findings"].append("未发现 JSON API")
                print(f"   ❌ 未发现 JSON API")

            if result["pagination_detected"]:
                result["key_findings"].append("检测到分页机制")
                print(f"   ✅ 检测到分页机制")
            else:
                print(f"   ❌ 未检测到分页机制")

            if result["anti_bot_detected"]:
                result["key_findings"].append(f"检测到反爬机制")
                print(f"   ⚠️ 检测到反爬机制")

            # Print all XHR URLs for reference
            print(f"\n[附录] 所有 XHR/Fetch URL:")
            for i, url in enumerate(result["all_xhr_urls"], 1):
                print(f"   {i}. {url[:150]}")

        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            result["error"] = str(e)
        finally:
            context.close()
            browser.close()
            pw.stop()

        return result


def main():
    output_dir = "/tmp/data_flow_analysis"
    os.makedirs(output_dir, exist_ok=True)

    all_results = []

    # Allow filtering by source
    filter_source = sys.argv[1] if len(sys.argv) > 1 else None

    targets = TARGETS
    if filter_source:
        targets = [t for t in TARGETS if t["source"].upper() == filter_source.upper()]

    print("=" * 70)
    print("数据链路分析工具")
    print(f"分析目标: {len(targets)} 个栏目")
    print("=" * 70)

    for target in targets:
        analyzer = DataFlowAnalyzer()
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
        print(f"  页面加载: {'✅' if r['page_loaded'] else '❌'}")
        print(f"  XHR/Fetch: {r['xhr_fetch_count']}")
        print(f"  JSON API: {len(r['json_apis'])}")
        print(f"  分页: {'✅' if r['pagination_detected'] else '❌'}")
        print(f"  Cookie依赖: {'✅' if r.get('cookies_count', 0) > 0 else '❌'} ({r.get('cookies_count', 0)} 个)")
        print(f"  Token依赖: {'⚠️' if r['token_dependency'] else '✅ 无'}")
        print(f"  浏览器必需: {'⚠️' if r['browser_required'] else '✅ 可能不需要'}")
        print(f"  反爬检测: {'⚠️' if r['anti_bot_detected'] else '✅ 未检测到'}")
        if r.get("error"):
            print(f"  错误: {r['error']}")

    print(f"\n✅ 所有结果已保存: {combined_path}")


if __name__ == "__main__":
    main()
