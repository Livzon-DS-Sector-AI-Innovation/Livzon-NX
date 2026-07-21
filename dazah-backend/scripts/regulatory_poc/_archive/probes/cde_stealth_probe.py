#!/usr/bin/env python3
"""
CDE 反检测浏览器探测脚本
使用反自动化指纹措施 + Xvfb 有头模式
"""

import os
import sys
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
    "--window-size=1920,1080",
]

STEALTH_INIT_SCRIPT = """
// 1. 移除 navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// 2. 覆盖 navigator.plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// 3. 覆盖 navigator.languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en'],
});

// 4. 覆盖 window.chrome
window.chrome = {runtime: {}};

// 5. 覆盖 permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({state: Notification.permission}) :
        originalQuery(parameters)
);

// 6. 覆盖 WebGL vendor/renderer
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, parameter);
};
"""


def probe():
    report = {
        "timestamp": datetime.now().isoformat(),
        "mode": "headed + stealth (Xvfb)",
        "display": os.environ.get("DISPLAY", "not set"),
        "captured_api_requests": [],
        "all_cde_responses": [],
        "cookies": [],
        "page_title": None,
        "page_url": None,
        "waf_passed": False,
        "api_found": False,
        "api_data": None,
        "pagination_data": None,
        "detail_page_data": None,
        "errors": [],
    }

    print("=" * 70)
    print("CDE 反检测浏览器探测 (Xvfb + Stealth)")
    print(f"DISPLAY = {report['display']}")
    print("=" * 70)

    pw = sync_playwright().start()

    try:
        print("\n[1] 启动有头浏览器 (反检测模式)...")
        browser = pw.chromium.launch(
            headless=False,
            executable_path="/tmp/playwright-browsers/chromium-1223/chrome-linux64/chrome",
            args=LAUNCH_ARGS,
            ignore_default_args=["--enable-automation"],
        )
        print("   ✅ 浏览器启动成功")
    except Exception as e:
        print(f"   ❌ 启动失败: {e}")
        report["errors"].append(str(e)[:500])
        pw.stop()
        return report

    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )

    # 注入反检测脚本
    context.add_init_script(STEALTH_INIT_SCRIPT)

    page = context.new_page()

    # 监听网络
    def on_response(response):
        url = response.url
        if "cde.org.cn" not in url:
            return
        entry = {
            "url": url[:300],
            "status": response.status,
            "content_type": response.headers.get("content-type", ""),
            "timestamp": datetime.now().isoformat(),
        }
        try:
            body = response.text()
            entry["body_length"] = len(body)
            if body.strip().startswith("{") or "json" in entry["content_type"]:
                try:
                    jd = json.loads(body)
                    entry["is_json"] = True
                    if isinstance(jd, dict):
                        entry["json_keys"] = list(jd.keys())
                        for k in ("records", "total", "pages", "current"):
                            if k in jd:
                                v = jd[k]
                                if isinstance(v, list):
                                    entry[f"field_{k}_len"] = len(v)
                                    if v and isinstance(v[0], dict):
                                        entry[f"field_{k}_item_keys"] = list(v[0].keys())
                                else:
                                    entry[f"field_{k}"] = v
                        entry["body_preview"] = body[:5000]
                except json.JSONDecodeError:
                    entry["is_json"] = False
            else:
                entry["is_json"] = False
        except Exception as ex:
            entry["body_error"] = str(ex)[:200]

        report["all_cde_responses"].append(entry)

        if "getDomesticGuideList" in url:
            report["api_found"] = True
            report["captured_api_requests"].append(entry)
            print(f"\n   🎯 捕获 getDomesticGuideList! status={response.status}")
            if entry.get("is_json"):
                print(f"      JSON keys: {entry.get('json_keys')}")
                report["api_data"] = entry

    page.on("response", on_response)

    # Step 2: 加载页面
    print("\n[2] 加载 CDE 指导原则页面...")
    try:
        page.goto("https://www.cde.org.cn/zdyz/index", timeout=30000, wait_until="domcontentloaded")
        print(f"   初始标题: '{page.title()}'")
    except Exception as e:
        print(f"   导航异常: {e}")

    # Step 3: 等待 WAF
    print("\n[3] 等待 WAF challenge...")
    waf_passed = False
    for i in range(15):
        time.sleep(2)
        title = page.title()
        url = page.url
        cookies = context.cookies()
        content_len = len(page.content())
        print(f"   [{(i+1)*2}s] title='{title[:40]}' cookies={len(cookies)} content={content_len}")

        if title and len(title.strip()) > 2:
            print(f"   ✅ WAF 通过! 标题: {title}")
            waf_passed = True
            break

        # 检查是否页面内容变大了（说明 WAF 通过了但标题可能还没更新）
        if content_len > 5000 and i > 3:
            # 检查是否有列表元素
            try:
                has_list = page.evaluate("() => document.querySelectorAll('a[href]').length > 10")
                if has_list:
                    print(f"   ✅ 检测到列表内容! content={content_len}")
                    waf_passed = True
                    break
            except Exception:
                pass

    report["waf_passed"] = waf_passed
    report["page_title"] = page.title()
    report["page_url"] = page.url

    # Step 4: Cookie 分析
    print("\n[4] Cookie 分析...")
    cookies = context.cookies()
    report["cookies"] = []
    for c in cookies:
        info = {
            "name": c["name"],
            "domain": c["domain"],
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", False),
            "expires": c.get("expires", -1),
            "value_length": len(c.get("value", "")),
        }
        if c.get("expires", -1) > 0:
            info["expires_human"] = datetime.fromtimestamp(c["expires"]).isoformat()
        report["cookies"].append(info)
        exp = info.get("expires_human", "Session")
        print(f"   {c['name']} @ {c['domain']} expires={exp} httpOnly={info['httpOnly']}")

    # Step 5: 如果 WAF 通过，等待 API 或手动触发
    if waf_passed:
        print("\n[5] 等待 API 自动触发...")
        page.wait_for_timeout(5000)

        if not report["api_found"]:
            print("   尝试滚动触发...")
            page.evaluate("window.scrollTo(0, 500)")
            page.wait_for_timeout(3000)

        if not report["api_found"]:
            print("   手动通过页面 fetch 调用...")
            try:
                fetch_result = page.evaluate("""async () => {
                    try {
                        const resp = await fetch('/zdyz/getDomesticGuideList?pageNum=1&pageSize=10', {
                            method: 'GET',
                            credentials: 'include',
                            headers: {
                                'Accept': 'application/json, text/plain, */*',
                                'X-Requested-With': 'XMLHttpRequest',
                            }
                        });
                        const text = await resp.text();
                        let parsed = null;
                        try { parsed = JSON.parse(text); } catch(e) {}
                        return {
                            status: resp.status,
                            url: resp.url,
                            body_length: text.length,
                            is_json: parsed !== null,
                            data: parsed,
                            body_preview: text.substring(0, 5000),
                        };
                    } catch(e) {
                        return {error: e.message};
                    }
                }""")
                print(f"   Fetch: status={fetch_result.get('status')} is_json={fetch_result.get('is_json')}")
                if fetch_result.get("is_json"):
                    data = fetch_result["data"]
                    print(f"   ✅ JSON! keys: {list(data.keys())}")
                    report["api_found"] = True
                    report["api_data"] = {
                        "url": fetch_result.get("url"),
                        "status": fetch_result["status"],
                        "is_json": True,
                        "json_keys": list(data.keys()),
                        "body_preview": fetch_result.get("body_preview", ""),
                    }
                    if "records" in data:
                        report["api_data"]["field_records_len"] = len(data["records"])
                        if data["records"]:
                            report["api_data"]["field_records_item_keys"] = list(data["records"][0].keys())
                            report["api_data"]["first_record"] = data["records"][0]
                    for k in ("total", "pages", "current"):
                        if k in data:
                            report["api_data"][f"field_{k}"] = data[k]
                else:
                    print(f"   预览: {fetch_result.get('body_preview', '')[:300]}")
            except Exception as e:
                print(f"   Fetch 异常: {e}")

    # Step 6: 分页测试
    if report["api_found"]:
        print("\n[6] 分页测试 pageNum=2...")
        try:
            p2 = page.evaluate("""async () => {
                try {
                    const resp = await fetch('/zdyz/getDomesticGuideList?pageNum=2&pageSize=10', {
                        method: 'GET', credentials: 'include',
                        headers: {'Accept': 'application/json'}
                    });
                    const text = await resp.text();
                    let parsed = null;
                    try { parsed = JSON.parse(text); } catch(e) {}
                    return {status: resp.status, is_json: parsed !== null, data: parsed, body_preview: text.substring(0, 3000)};
                } catch(e) { return {error: e.message}; }
            }""")
            print(f"   Page2: status={p2.get('status')} is_json={p2.get('is_json')}")
            if p2.get("is_json") and p2.get("data"):
                d2 = p2["data"]
                print(f"   ✅ 第二页! current={d2.get('current')} records={len(d2.get('records', []))}")
                report["pagination_data"] = {
                    "page2_current": d2.get("current"),
                    "page2_total": d2.get("total"),
                    "page2_records_len": len(d2.get("records", [])),
                    "page2_first_record": d2.get("records", [{}])[0] if d2.get("records") else None,
                }
        except Exception as e:
            print(f"   异常: {e}")

    # Step 7: 详情页测试
    if report.get("api_data") and report["api_data"].get("first_record"):
        zdyz_id = report["api_data"]["first_record"].get("zdyzIdCODE")
        if zdyz_id:
            print(f"\n[7] 详情页测试 zdyzIdCODE={zdyz_id}...")
            detail_url = f"/zdyz/domesticinfopage?zdyzIdCODE={zdyz_id}"
            try:
                dr = page.evaluate(f"""async () => {{
                    try {{
                        const resp = await fetch('{detail_url}', {{method: 'GET', credentials: 'include'}});
                        const text = await resp.text();
                        return {{
                            status: resp.status,
                            url: resp.url,
                            body_length: text.length,
                            is_html: text.includes('<html') || text.includes('<!DOCTYPE'),
                            title_match: text.includes('指导原则') || text.includes('指南'),
                            body_preview: text.substring(0, 1000),
                        }};
                    }} catch(e) {{ return {{error: e.message}}; }}
                }}""")
                print(f"   详情页: status={dr.get('status')} length={dr.get('body_length')} is_html={dr.get('is_html')}")
                report["detail_page_data"] = {
                    "zdyzIdCODE": zdyz_id,
                    "detail_url": detail_url,
                    "http_status": dr.get("status"),
                    "body_length": dr.get("body_length"),
                    "is_html": dr.get("is_html"),
                }
            except Exception as e:
                print(f"   异常: {e}")

    # 截图
    try:
        page.screenshot(path="/tmp/cde_stealth_screenshot.png")
        print("\n[截图] /tmp/cde_stealth_screenshot.png")
    except Exception:
        pass

    context.close()
    browser.close()
    pw.stop()
    return report


def main():
    report = probe()

    output_path = "/tmp/cde_stealth_probe_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n\n{'='*70}")
    print("探测结果汇总")
    print(f"{'='*70}")
    print(f"  模式: {report['mode']}")
    print(f"  WAF 通过: {'✅' if report['waf_passed'] else '❌'}")
    print(f"  API 捕获: {'✅' if report['api_found'] else '❌'}")
    print(f"  页面标题: {report['page_title']}")
    print(f"  总响应数: {len(report['all_cde_responses'])}")
    print(f"  Cookie 数: {len(report['cookies'])}")

    if report["api_data"]:
        ad = report["api_data"]
        print(f"\n  API 数据:")
        print(f"    URL: {ad.get('url', 'N/A')[:150]}")
        print(f"    Status: {ad.get('status')}")
        if ad.get("is_json"):
            print(f"    JSON keys: {ad.get('json_keys')}")
            if 'field_records_len' in ad:
                print(f"    records: {ad['field_records_len']} 条")
            if 'field_total' in ad:
                print(f"    total: {ad['field_total']}")
            if 'first_record' in ad:
                print(f"    首条: {json.dumps(ad['first_record'], ensure_ascii=False)[:300]}")

    if report["pagination_data"]:
        pd = report["pagination_data"]
        print(f"\n  分页数据:")
        print(f"    Page2 current: {pd.get('page2_current')}")
        print(f"    Page2 records: {pd.get('page2_records_len')}")
        if pd.get("page2_first_record"):
            print(f"    Page2 首条: {json.dumps(pd['page2_first_record'], ensure_ascii=False)[:200]}")

    if report["detail_page_data"]:
        dd = report["detail_page_data"]
        print(f"\n  详情页:")
        print(f"    zdyzIdCODE: {dd.get('zdyzIdCODE')}")
        print(f"    URL: {dd.get('detail_url')}")
        print(f"    Status: {dd.get('http_status')}")
        print(f"    Length: {dd.get('body_length')}")

    print(f"\n💾 {output_path}")


if __name__ == "__main__":
    main()
