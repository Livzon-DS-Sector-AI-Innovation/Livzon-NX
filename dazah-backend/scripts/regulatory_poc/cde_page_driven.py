#!/usr/bin/env python3
"""
CDE 页面驱动采集脚本
只监听页面自身发出的请求，不手动构造任何 API 调用
通过点击分页按钮触发翻页
"""

import os
import json
import time
import threading
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

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
window.chrome = {runtime: {}};
const origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (p) => (
    p.name === 'notifications' ? Promise.resolve({state: Notification.permission}) : origQuery(p)
);
"""


def main():
    output = {
        "timestamp": datetime.now().isoformat(),
        "approach": "page-driven (listen only, no manual API calls)",
        "target_url": "https://www.cde.org.cn/zdyz/index",
        "waf_passed": False,
        "page_title": None,
        "captured_pages": [],
        "all_api_responses": [],
        "pagination_works": None,
        "cookies": [],
        "errors": [],
    }

    print("=" * 70)
    print("CDE 页面驱动采集 (只监听，不构造)")
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
        timezone_id="Asia/Shanghai",
    )
    context.add_init_script(STEALTH_JS)
    page = context.new_page()

    # 用于存储捕获的 getDomesticGuideList 响应
    guide_list_responses = []
    page_load_event = threading.Event()

    def on_response(response):
        url = response.url
        if "cde.org.cn" not in url:
            return

        # 记录所有 JSON API 响应
        ct = response.headers.get("content-type", "")
        if "json" in ct or "getDomesticGuideList" in url or "homepageNewsList" in url:
            try:
                body = response.text()
                jd = json.loads(body) if body.strip().startswith("{") else None
                entry = {
                    "url": url,
                    "status": response.status,
                    "timestamp": datetime.now().isoformat(),
                    "is_json": jd is not None,
                }
                if jd:
                    entry["json_keys"] = list(jd.keys())
                    entry["data"] = jd
                output["all_api_responses"].append(entry)

                # 专门捕获 getDomesticGuideList
                if "getDomesticGuideList" in url:
                    parsed = urlparse(url)
                    params = parse_qs(parsed.query)
                    page_num = int(params.get("pageNum", [0])[0])
                    page_size = int(params.get("pageSize", [0])[0])
                    mmewmd = params.get("MmEwMD", [""])[0]

                    capture = {
                        "page_num": page_num,
                        "page_size": page_size,
                        "mmewmd_present": bool(mmewmd),
                        "mmewmd_length": len(mmewmd),
                        "full_url": url,
                        "http_status": response.status,
                        "response_data": jd,
                        "timestamp": datetime.now().isoformat(),
                    }

                    if jd and jd.get("code") == 200:
                        records = jd.get("data", {}).get("records", []) if isinstance(jd.get("data"), dict) else jd.get("records", [])
                        total = jd.get("data", {}).get("total") if isinstance(jd.get("data"), dict) else jd.get("total")
                        pages = jd.get("data", {}).get("pages") if isinstance(jd.get("data"), dict) else jd.get("pages")
                        current = jd.get("data", {}).get("current") if isinstance(jd.get("data"), dict) else jd.get("current")
                        capture["records_count"] = len(records)
                        capture["total"] = total
                        capture["pages"] = pages
                        capture["current"] = current
                        capture["records"] = records
                        capture["success"] = True
                        print(f"\n   🎯 getDomesticGuideList page={page_num} | records={len(records)} total={total} current={current}")
                    else:
                        capture["success"] = False
                        capture["msg"] = jd.get("msg") if jd else "non-JSON"
                        print(f"\n   ⚠️ getDomesticGuideList page={page_num} | msg={capture.get('msg')}")

                    guide_list_responses.append(capture)

            except Exception as ex:
                pass

    page.on("response", on_response)

    # Step 2: 加载页面
    print("\n[2] 加载 CDE 指导原则页面...")
    try:
        page.goto("https://www.cde.org.cn/zdyz/index", timeout=30000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"   导航异常: {e}")

    # Step 3: 等待 WAF
    print("\n[3] 等待 WAF 通过...")
    for i in range(15):
        time.sleep(2)
        title = page.title()
        content_len = len(page.content())
        print(f"   [{(i+1)*2}s] title='{title[:40]}' content={content_len}")
        if title and len(title.strip()) > 2:
            print(f"   ✅ WAF 通过! 标题: {title}")
            output["waf_passed"] = True
            break

    output["page_title"] = page.title()

    if not output["waf_passed"]:
        print("   ❌ WAF 未通过，无法继续")
        _cleanup(context, browser, pw, output)
        return

    # Step 4: 等待页面 API 加载
    print("\n[4] 等待页面 API 自动加载...")
    page.wait_for_timeout(5000)

    # 检查是否已经有 getDomesticGuideList 响应
    print(f"   已捕获 getDomesticGuideList 响应: {len(guide_list_responses)}")

    # 也检查其他 API
    other_apis = [r for r in output["all_api_responses"] if "getDomesticGuideList" not in r["url"]]
    print(f"   其他 API 响应: {len(other_apis)}")
    for r in other_apis:
        url_short = r["url"].split("?")[0].split("/")[-1] if "?" in r["url"] else r["url"].split("/")[-1]
        print(f"      {r['status']} {url_short[:60]} keys={r.get('json_keys', 'N/A')}")

    # Step 5: 如果首页没有触发 getDomesticGuideList，尝试点击相关 tab/链接
    if len(guide_list_responses) == 0:
        print("\n[5] 页面未自动调用 getDomesticGuideList，尝试点击页面元素...")

        # 截图看当前页面状态
        page.screenshot(path="/tmp/cde_page_step5.png")

        # 列出所有可点击的链接/按钮
        links = page.evaluate("""() => {
            const els = document.querySelectorAll('a, button, [onclick], [role="tab"], .tab-item, .nav-item');
            return Array.from(els).map(el => ({
                tag: el.tagName,
                text: el.textContent.trim().substring(0, 50),
                href: el.href || '',
                class: el.className || '',
                id: el.id || '',
            })).filter(el => el.text.length > 0);
        }""")
        print(f"   找到 {len(links)} 个可交互元素:")
        for l in links[:20]:
            print(f"      <{l['tag']}> '{l['text']}' class='{l['class'][:40]}' href='{l['href'][:60]}'")

        # 尝试点击包含"指导原则"或"国内"的元素
        clicked = False
        for selector in [
            "text=指导原则",
            "text=国内指导原则",
            "text=技术指导原则",
            "a:has-text('指导原则')",
            ".tab-item:has-text('指导原则')",
            "[class*='tab']:has-text('指导原则')",
        ]:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    print(f"\n   点击: {selector}")
                    el.click()
                    page.wait_for_timeout(3000)
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            print("   未找到可点击的指导原则元素")

    # Step 6: 检查首页数据
    print(f"\n[6] 当前已捕获 getDomesticGuideList: {len(guide_list_responses)} 次")

    # 如果还没有，尝试找到并点击分页区域附近的"更多"或列表区域
    if len(guide_list_responses) == 0:
        print("   尝试查找列表区域...")
        # 检查页面上是否有列表内容
        list_content = page.evaluate("""() => {
            const items = document.querySelectorAll('.list-item, .guide-item, [class*="list"] li, .zdyz-list');
            return items.length;
        }""")
        print(f"   列表项数量: {list_content}")

        # 尝试滚动到列表区域
        page.evaluate("window.scrollTo(0, 300)")
        page.wait_for_timeout(2000)

    # Step 7: 翻页测试 - 通过点击分页按钮
    print(f"\n[7] 翻页测试...")
    page.screenshot(path="/tmp/cde_page_before_pagination.png")

    # 查找分页元素
    pagination_info = page.evaluate("""() => {
        // 查找分页相关元素
        const selectors = [
            '.pagination', '.pager', '[class*="paging"]', '[class*="page"]',
            '.el-pagination', '.ant-pagination',
            'a:has-text("下一页")', 'button:has-text("下一页")',
            'a:has-text(">>")', 'a:has-text("›")',
            '[class*="next"]', '.page-next',
        ];
        const found = [];
        for (const sel of selectors) {
            try {
                const els = document.querySelectorAll(sel);
                els.forEach(el => {
                    found.push({
                        selector: sel,
                        tag: el.tagName,
                        text: el.textContent.trim().substring(0, 50),
                        class: el.className.substring(0, 60),
                        visible: el.offsetParent !== null,
                    });
                });
            } catch(e) {}
        }
        return found;
    }""")

    print(f"   找到 {len(pagination_info)} 个分页相关元素:")
    for p in pagination_info[:10]:
        print(f"      [{p['selector']}] <{p['tag']}> '{p['text']}' visible={p['visible']}")

    # 尝试点击下一页
    pages_captured = len(guide_list_responses)
    next_btn_selectors = [
        "a:has-text('下一页')",
        "button:has-text('下一页')",
        ".next a",
        "a.next",
        "[class*='next']",
        ".el-pagination .btn-next",
        ".ant-pagination-next",
        "a:has-text('>')",
        "li.next > a",
    ]

    for attempt in range(3):  # 尝试翻 3 页
        before_count = len(guide_list_responses)
        clicked_next = False

        for sel in next_btn_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    print(f"\n   点击翻页 [{attempt+1}]: {sel}")
                    el.click()
                    page.wait_for_timeout(4000)
                    clicked_next = True
                    break
            except Exception:
                continue

        if not clicked_next:
            # 尝试通过 JS 点击
            try:
                clicked = page.evaluate("""() => {
                    const btns = document.querySelectorAll('a, button, li');
                    for (const b of btns) {
                        const text = b.textContent.trim();
                        if (text === '下一页' || text === '>' || text === '›' || text === '>>') {
                            b.click();
                            return text;
                        }
                    }
                    // 尝试点击页码数字
                    const pageNums = document.querySelectorAll('.el-pager li, .ant-pagination-item a, [class*="page-num"]');
                    for (const pn of pageNums) {
                        const text = pn.textContent.trim();
                        if (text === '""" + str(attempt + 2) + """') {
                            pn.click();
                            return 'page_' + text;
                        }
                    }
                    return null;
                }""")
                if clicked:
                    print(f"   JS 点击翻页 [{attempt+1}]: {clicked}")
                    page.wait_for_timeout(4000)
                    clicked_next = True
            except Exception as e:
                print(f"   JS 点击异常: {e}")

        after_count = len(guide_list_responses)
        new_captures = after_count - before_count

        if new_captures > 0:
            print(f"   ✅ 翻页 {attempt+1} 成功! 新捕获 {new_captures} 个响应")
        else:
            print(f"   ⚠️ 翻页 {attempt+1} 未触发新请求")

        page.screenshot(path=f"/tmp/cde_page_after_page{attempt+2}.png")

    # Step 8: 保存结果
    print(f"\n[8] 保存结果...")

    # 整理捕获的页面数据
    for cap in guide_list_responses:
        page_data = {
            "page_num": cap.get("page_num"),
            "http_status": cap.get("http_status"),
            "success": cap.get("success"),
            "records_count": cap.get("records_count", 0),
            "total": cap.get("total"),
            "pages": cap.get("pages"),
            "current": cap.get("current"),
            "mmewmd_present": cap.get("mmewmd_present"),
            "mmewmd_length": cap.get("mmewmd_length"),
            "timestamp": cap.get("timestamp"),
            "records": cap.get("records", []),
            "msg": cap.get("msg"),
        }
        output["captured_pages"].append(page_data)

    # 判断分页是否有效
    successful_pages = [p for p in output["captured_pages"] if p["success"]]
    if len(successful_pages) >= 2:
        # 检查不同页的数据是否不同
        first_ids = set()
        second_ids = set()
        if successful_pages[0].get("records"):
            first_ids = {r.get("zdyzIdCODE") or r.get("id") or r.get("title") for r in successful_pages[0]["records"]}
        if successful_pages[1].get("records"):
            second_ids = {r.get("zdyzIdCODE") or r.get("id") or r.get("title") for r in successful_pages[1]["records"]}
        output["pagination_works"] = len(first_ids) > 0 and len(second_ids) > 0 and first_ids != second_ids
    elif len(successful_pages) == 1:
        output["pagination_works"] = "only_page1_captured"
    else:
        output["pagination_works"] = False

    # Cookie 快照
    cookies = context.cookies()
    output["cookies"] = [
        {"name": c["name"], "domain": c["domain"], "expires": c.get("expires", -1),
         "expires_human": datetime.fromtimestamp(c["expires"]).isoformat() if c.get("expires", 0) > 0 else "Session",
         "httpOnly": c.get("httpOnly", False)}
        for c in cookies
    ]

    _cleanup(context, browser, pw, output)
    _save(output)
    _print_summary(output)


def _save(output):
    path = "/home/chenyingying/dazah/dazah-backend/scripts/regulatory_poc/cde_guideline_pages_1_3.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n💾 数据已保存: {path}")


def _cleanup(context, browser, pw, output):
    try:
        context.close()
        browser.close()
        pw.stop()
    except Exception:
        pass


def _print_summary(output):
    print(f"\n\n{'='*70}")
    print("最终报告")
    print(f"{'='*70}")
    print(f"  WAF 通过: {'✅' if output['waf_passed'] else '❌'}")
    print(f"  页面标题: {output['page_title']}")
    print(f"  捕获 getDomesticGuideList 次数: {len(output['captured_pages'])}")
    print(f"  总 API 响应数: {len(output['all_api_responses'])}")
    print(f"  分页有效: {output['pagination_works']}")

    for i, p in enumerate(output["captured_pages"], 1):
        status = "✅" if p["success"] else "❌"
        print(f"\n  [{status}] Page {p['page_num']}:")
        print(f"      HTTP: {p['http_status']}")
        print(f"      MmEwMD: {'有' if p['mmewmd_present'] else '无'} (长度: {p.get('mmewmd_length', 0)})")
        if p["success"]:
            print(f"      records: {p['records_count']} 条")
            print(f"      total: {p['total']}")
            print(f"      current: {p['current']}")
            print(f"      pages: {p['pages']}")
            if p.get("records"):
                first = p["records"][0]
                print(f"      首条: {first.get('title', 'N/A')[:60]}")
        else:
            print(f"      msg: {p.get('msg', 'N/A')}")

    # Cookie 信息
    print(f"\n  Cookies ({len(output['cookies'])} 个):")
    for c in output["cookies"]:
        print(f"      {c['name']} @ {c['domain']} expires={c['expires_human']}")

    # 其他 API
    other = [r for r in output["all_api_responses"] if "getDomesticGuideList" not in r["url"]]
    if other:
        print(f"\n  其他 API 响应 ({len(other)} 个):")
        for r in other:
            url_short = r["url"].split("?")[0]
            print(f"      {r['status']} {url_short[:80]}")
            if r.get("is_json") and r.get("data"):
                d = r["data"]
                if isinstance(d, dict) and "data" in d:
                    data_val = d["data"]
                    if isinstance(data_val, list):
                        print(f"         data: list[{len(data_val)}]")
                        if data_val and isinstance(data_val[0], dict):
                            print(f"         首条: {data_val[0].get('title', 'N/A')[:60]}")


if __name__ == "__main__":
    main()
