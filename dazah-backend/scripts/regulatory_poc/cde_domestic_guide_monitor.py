#!/usr/bin/env python3
"""
CDE 国内药品技术指导原则页面监听脚本
直接打开目标页面，只监听不构造
"""

import os
import json
import time
from datetime import datetime
from urllib.parse import urlparse, parse_qs

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/playwright-browsers"

from playwright.sync_api import sync_playwright

LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
]

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
window.chrome = {runtime: {}};
"""

TARGET_URL = "https://www.cde.org.cn/zdyz/listpage/9cd8db3b7530c6fa0c86485e563f93c7"

def main():
    output = {
        "timestamp": datetime.now().isoformat(),
        "target_url": TARGET_URL,
        "approach": "direct page load + listen only",
        "waf_passed": False,
        "page_title": None,
        "all_xhr_fetch": [],
        "getDomesticGuideList_captured": [],
        "cookies": [],
        "errors": [],
    }

    print("=" * 70)
    print("CDE 国内药品技术指导原则 - 接口监听")
    print(f"目标: {TARGET_URL}")
    print("=" * 70)

    pw = sync_playwright().start()

    # 启动浏览器
    print("\n[1] 启动反检测浏览器...")
    try:
        browser = pw.chromium.launch(
            headless=False,
            executable_path="/tmp/playwright-browsers/chromium-1223/chrome-linux64/chrome",
            args=LAUNCH_ARGS,
            ignore_default_args=["--enable-automation"],
        )
        print("   ✅ 启动成功")
    except Exception as e:
        print(f"   ❌ {e}")
        output["errors"].append(str(e)[:500])
        pw.stop()
        _save(output)
        return

    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        locale="zh-CN",
    )
    context.add_init_script(STEALTH_JS)
    page = context.new_page()

    # 监听所有 XHR/Fetch
    def on_response(response):
        url = response.url
        if "cde.org.cn" not in url:
            return

        req = response.request
        resource_type = req.resource_type

        # 只记录 XHR 和 Fetch
        if resource_type not in ("xhr", "fetch"):
            return

        entry = {
            "url": url,
            "method": req.method,
            "resource_type": resource_type,
            "status": response.status,
            "timestamp": datetime.now().isoformat(),
        }

        # 提取请求参数
        if req.method == "POST" and req.post_data:
            entry["post_data"] = req.post_data
            try:
                entry["post_json"] = json.loads(req.post_data)
            except:
                pass

        # 解析 URL 参数
        parsed = urlparse(url)
        if parsed.query:
            entry["query_params"] = parse_qs(parsed.query)

        # 读取响应
        try:
            body = response.text()
            entry["response_length"] = len(body)
            if body.strip().startswith("{") or "json" in response.headers.get("content-type", ""):
                try:
                    jd = json.loads(body)
                    entry["is_json"] = True
                    entry["response_json"] = jd
                    if isinstance(jd, dict):
                        entry["json_keys"] = list(jd.keys())
                        # 提取关键字段
                        for k in ("records", "total", "pages", "current", "data"):
                            if k in jd:
                                v = jd[k]
                                if isinstance(v, list):
                                    entry[f"field_{k}_len"] = len(v)
                                elif isinstance(v, (int, float)):
                                    entry[f"field_{k}"] = v
                except json.JSONDecodeError:
                    entry["is_json"] = False
            else:
                entry["is_json"] = False
                entry["response_preview"] = body[:500]
        except Exception as ex:
            entry["body_error"] = str(ex)[:200]

        output["all_xhr_fetch"].append(entry)

        # 特别记录 getDomesticGuideList
        if "getDomesticGuideList" in url:
            output["getDomesticGuideList_captured"].append(entry)
            print(f"\n   🎯 getDomesticGuideList | status={response.status}")
            if entry.get("is_json"):
                print(f"      keys: {entry.get('json_keys')}")
                if "field_records_len" in entry:
                    print(f"      records: {entry['field_records_len']}")
                if "field_total" in entry:
                    print(f"      total: {entry['field_total']}")

    page.on("response", on_response)

    # 加载目标页面
    print(f"\n[2] 加载页面: {TARGET_URL}")
    try:
        page.goto(TARGET_URL, timeout=30000, wait_until="domcontentloaded")
        print(f"   初始标题: '{page.title()}'")
    except Exception as e:
        print(f"   导航异常: {e}")

    # 等待 WAF
    print("\n[3] 等待 WAF 通过...")
    for i in range(15):
        time.sleep(2)
        title = page.title()
        content_len = len(page.content())
        print(f"   [{(i+1)*2}s] title='{title[:50]}' content={content_len}")
        if title and len(title.strip()) > 2:
            print(f"   ✅ WAF 通过! 标题: {title}")
            output["waf_passed"] = True
            break

    output["page_title"] = page.title()

    if not output["waf_passed"]:
        print("   ❌ WAF 未通过")
        _cleanup(context, browser, pw, output)
        _save(output)
        return

    # 等待页面 API 加载
    print("\n[4] 等待页面 API 加载...")
    page.wait_for_timeout(5000)

    # 截图
    page.screenshot(path="/tmp/cde_domestic_guide_page.png")
    print("   截图: /tmp/cde_domestic_guide_page.png")

    # 统计
    print(f"\n[5] 监听结果:")
    print(f"   总 XHR/Fetch: {len(output['all_xhr_fetch'])}")
    print(f"   getDomesticGuideList: {len(output['getDomesticGuideList_captured'])}")

    # 列出所有接口
    print(f"\n[6] 所有接口列表:")
    for i, entry in enumerate(output["all_xhr_fetch"], 1):
        url_short = entry["url"].split("?")[0]
        api_name = url_short.split("/")[-1]
        print(f"   [{i}] {entry['status']} {entry['method']} {api_name}")
        if entry.get("is_json"):
            print(f"       keys: {entry.get('json_keys')}")
            if "field_records_len" in entry:
                print(f"       records: {entry['field_records_len']}")
            if "field_total" in entry:
                print(f"       total: {entry['field_total']}")

    # Cookie
    cookies = context.cookies()
    output["cookies"] = [
        {"name": c["name"], "domain": c["domain"],
         "expires_human": datetime.fromtimestamp(c["expires"]).isoformat() if c.get("expires", 0) > 0 else "Session"}
        for c in cookies
    ]

    _cleanup(context, browser, pw, output)
    _save(output)
    _print_summary(output)


def _save(output):
    path = "/home/chenyingying/dazah/dazah-backend/scripts/regulatory_poc/cde_domestic_guide_monitor.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n💾 已保存: {path}")


def _cleanup(context, browser, pw, output):
    try:
        context.close()
        browser.close()
        pw.stop()
    except:
        pass


def _print_summary(output):
    print(f"\n\n{'='*70}")
    print("最终报告")
    print(f"{'='*70}")
    print(f"  WAF 通过: {'✅' if output['waf_passed'] else '❌'}")
    print(f"  页面标题: {output['page_title']}")
    print(f"  总 XHR/Fetch: {len(output['all_xhr_fetch'])}")
    print(f"  getDomesticGuideList: {len(output['getDomesticGuideList_captured'])}")

    if output["getDomesticGuideList_captured"]:
        print(f"\n  getDomesticGuideList 详情:")
        for i, cap in enumerate(output["getDomesticGuideList_captured"], 1):
            print(f"\n  [{i}] {cap['method']} {cap['url'][:150]}")
            print(f"      Status: {cap['status']}")
            if cap.get("query_params"):
                print(f"      参数: {json.dumps(cap['query_params'], ensure_ascii=False)[:200]}")
            if cap.get("is_json") and cap.get("response_json"):
                jd = cap["response_json"]
                print(f"      响应 keys: {list(jd.keys())}")
                if "data" in jd and isinstance(jd["data"], dict):
                    data = jd["data"]
                    print(f"      data.total: {data.get('total')}")
                    print(f"      data.pages: {data.get('pages')}")
                    print(f"      data.current: {data.get('current')}")
                    records = data.get("records", [])
                    print(f"      data.records: {len(records)} 条")
                    if records:
                        print(f"      首条: {records[0].get('title', 'N/A')[:60]}")

    print(f"\n  Cookies ({len(output['cookies'])} 个):")
    for c in output["cookies"][:5]:
        print(f"      {c['name']} @ {c['domain']} expires={c['expires_human']}")


if __name__ == "__main__":
    main()
