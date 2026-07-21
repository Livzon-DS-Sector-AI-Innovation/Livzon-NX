#!/usr/bin/env python3
"""
CDE 有头浏览器探测脚本
在真实浏览器窗口环境下监听 getDomesticGuideList 接口
"""

import os
import sys
import json
import time
from datetime import datetime
from urllib.parse import urlparse, parse_qs

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/playwright-browsers"
# DISPLAY is set by xvfb-run

from playwright.sync_api import sync_playwright


LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]


def probe():
    report = {
        "timestamp": datetime.now().isoformat(),
        "mode": "headed (Xvfb)",
        "display": os.environ.get("DISPLAY"),
        "captured_requests": [],
        "captured_responses": [],
        "cookies_before": [],
        "cookies_after": [],
        "page_title": None,
        "page_url": None,
        "waf_passed": False,
        "api_found": False,
        "api_data": None,
        "errors": [],
    }

    print("=" * 70)
    print("CDE 有头浏览器探测 (Xvfb)")
    print(f"DISPLAY = {os.environ.get('DISPLAY')}")
    print("=" * 70)

    pw = sync_playwright().start()

    try:
        print("\n[1] 启动有头浏览器...")
        browser = pw.chromium.launch(
            headless=False,
            executable_path="/tmp/playwright-browsers/chromium-1223/chrome-linux64/chrome",
            args=LAUNCH_ARGS,
        )
        print("   ✅ 有头浏览器启动成功")
    except Exception as e:
        print(f"   ❌ 启动失败: {e}")
        report["errors"].append(str(e))
        pw.stop()
        return report

    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    page = context.new_page()

    # 记录所有请求和响应
    def on_request(request):
        url = request.url
        if "cde.org.cn" in url:
            entry = {
                "url": url,
                "method": request.method,
                "resource_type": request.resource_type,
                "post_data": request.post_data,
                "timestamp": datetime.now().isoformat(),
            }
            report["captured_requests"].append(entry)
            rtype = "API" if request.resource_type in ("xhr", "fetch") else request.resource_type[:3].upper()
            print(f"   [REQ {rtype}] {request.method} {url[:130]}")

    def on_response(response):
        url = response.url
        if "cde.org.cn" not in url:
            return
        entry = {
            "url": url,
            "status": response.status,
            "content_type": response.headers.get("content-type", ""),
            "timestamp": datetime.now().isoformat(),
        }
        # 尝试读取响应体
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
                        entry["body_preview"] = body[:3000]
                except json.JSONDecodeError:
                    entry["is_json"] = False
            else:
                entry["is_json"] = False
                entry["body_preview"] = body[:500]
        except Exception as ex:
            entry["body_error"] = str(ex)

        report["captured_responses"].append(entry)

        # 检查是否是目标 API
        if "getDomesticGuideList" in url:
            report["api_found"] = True
            print(f"\n   🎯🎯🎯 捕获到 getDomesticGuideList!")
            print(f"       状态: {response.status}")
            if entry.get("is_json"):
                print(f"       JSON keys: {entry.get('json_keys')}")
                if "field_records_len" in entry:
                    print(f"       records: {entry['field_records_len']} 条")
                if "field_total" in entry:
                    print(f"       total: {entry['field_total']}")
                report["api_data"] = entry
            else:
                print(f"       非 JSON 响应")

    page.on("request", on_request)
    page.on("response", on_response)

    # Step 2: 加载页面
    print("\n[2] 加载 CDE 指导原则页面...")
    try:
        page.goto("https://www.cde.org.cn/zdyz/index", timeout=30000, wait_until="domcontentloaded")
        print(f"   初始标题: '{page.title()}'")
    except Exception as e:
        print(f"   页面导航异常: {e}")

    # Step 3: 等待 WAF challenge
    print("\n[3] 等待 WAF challenge 完成...")
    for i in range(12):
        time.sleep(2)
        title = page.title()
        url = page.url
        cookies = context.cookies()
        print(f"   [{(i+1)*2}s] title='{title}' url={url[:80]} cookies={len(cookies)}")

        if title and len(title) > 2:
            print(f"   ✅ 页面标题出现: {title}")
            report["waf_passed"] = True
            break

    report["page_title"] = page.title()
    report["page_url"] = page.url

    # Step 4: 记录 Cookie
    print("\n[4] Cookie 快照...")
    cookies = context.cookies()
    report["cookies_after"] = [
        {"name": c["name"], "domain": c["domain"], "expires": c.get("expires", -1),
         "httpOnly": c.get("httpOnly", False), "value_preview": c["value"][:80]}
        for c in cookies
    ]
    for c in report["cookies_after"]:
        exp = datetime.fromtimestamp(c["expires"]).isoformat() if c["expires"] > 0 else "Session"
        print(f"   {c['name']} @ {c['domain']} expires={exp}")

    # Step 5: 如果 WAF 通过了但 API 还没触发，等待更久或滚动触发
    if report["waf_passed"] and not report["api_found"]:
        print("\n[5] WAF 已通过，等待 API 自动触发...")
        page.wait_for_timeout(5000)

        if not report["api_found"]:
            print("   尝试滚动页面触发懒加载...")
            page.evaluate("window.scrollTo(0, 500)")
            page.wait_for_timeout(3000)

        if not report["api_found"]:
            print("   尝试点击页面元素触发请求...")
            try:
                page.click("body")
                page.wait_for_timeout(3000)
            except Exception:
                pass

    # Step 6: 如果 API 还没触发，手动通过页面内 fetch 调用
    if report["waf_passed"] and not report["api_found"]:
        print("\n[6] 手动通过页面上下文调用 fetch...")
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
                        body_preview: text.substring(0, 3000),
                    };
                } catch(e) {
                    return {error: e.message};
                }
            }""")
            print(f"   Fetch 结果: status={fetch_result.get('status')}")
            if fetch_result.get("is_json"):
                data = fetch_result["data"]
                print(f"   ✅ JSON 响应! keys: {list(data.keys())}")
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
                print(f"   响应预览: {fetch_result.get('body_preview', '')[:300]}")
        except Exception as e:
            print(f"   Fetch 异常: {e}")

    # 最终截图
    try:
        page.screenshot(path="/tmp/cde_probe_screenshot.png")
        print("\n[截图] 已保存: /tmp/cde_probe_screenshot.png")
    except Exception:
        pass

    # 清理
    context.close()
    browser.close()
    pw.stop()

    return report


def main():
    report = probe()

    # 保存结果
    output_path = "/tmp/cde_headed_probe_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 打印汇总
    print(f"\n\n{'='*70}")
    print("探测结果汇总")
    print(f"{'='*70}")
    print(f"  模式: {report['mode']}")
    print(f"  WAF 通过: {'✅' if report['waf_passed'] else '❌'}")
    print(f"  API 捕获: {'✅' if report['api_found'] else '❌'}")
    print(f"  页面标题: {report['page_title']}")
    print(f"  捕获请求数: {len(report['captured_requests'])}")
    print(f"  捕获响应数: {len(report['captured_responses'])}")
    print(f"  Cookie 数: {len(report['cookies_after'])}")

    if report["api_data"]:
        print(f"\n  API 数据:")
        print(f"    URL: {report['api_data'].get('url', 'N/A')}")
        print(f"    Status: {report['api_data'].get('status')}")
        if report['api_data'].get('is_json'):
            print(f"    JSON keys: {report['api_data'].get('json_keys')}")
            if 'field_records_len' in report['api_data']:
                print(f"    records: {report['api_data']['field_records_len']} 条")
            if 'field_total' in report['api_data']:
                print(f"    total: {report['api_data']['field_total']}")
            if 'first_record' in report['api_data']:
                print(f"    首条记录: {json.dumps(report['api_data']['first_record'], ensure_ascii=False)[:300]}")

    if report["errors"]:
        print(f"\n  错误:")
        for e in report["errors"]:
            print(f"    - {e}")

    print(f"\n💾 结果已保存: {output_path}")


if __name__ == "__main__":
    main()
