#!/usr/bin/env python3
"""
CDE 国内药品技术指导原则 - 翻页测试
测试分页功能，验证不同页的数据是否不同
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
        "approach": "page-driven pagination test",
        "waf_passed": False,
        "page_title": None,
        "pagination_events": [],
        "all_xhr_fetch": [],
        "getDomesticGuideList_captured": [],
        "cookies": [],
        "errors": [],
    }

    print("=" * 70)
    print("CDE 国内药品技术指导原则 - 翻页测试")
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

        if resource_type not in ("xhr", "fetch"):
            return

        entry = {
            "url": url,
            "method": req.method,
            "resource_type": resource_type,
            "status": response.status,
            "timestamp": datetime.now().isoformat(),
        }

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
                                    # 记录第一条记录的标题用于对比
                                    if k == "records" and v and isinstance(v[0], dict):
                                        entry["first_record_title"] = v[0].get("title", "")
                                elif isinstance(v, (int, float)):
                                    entry[f"field_{k}"] = v
                                elif isinstance(v, dict) and k == "data":
                                    # data 字段包含分页信息
                                    if "total" in v:
                                        entry["field_total"] = v["total"]
                                    if "pages" in v:
                                        entry["field_pages"] = v["pages"]
                                    if "current" in v:
                                        entry["field_current"] = v["current"]
                                    if "records" in v:
                                        records = v["records"]
                                        entry["field_records_len"] = len(records)
                                        if records and isinstance(records[0], dict):
                                            entry["first_record_title"] = records[0].get("title", "")
                except json.JSONDecodeError:
                    entry["is_json"] = False
            else:
                entry["is_json"] = False
        except Exception as ex:
            entry["body_error"] = str(ex)[:200]

        output["all_xhr_fetch"].append(entry)

        # 特别记录 getDomesticGuideList
        if "getDomesticGuideList" in url:
            output["getDomesticGuideList_captured"].append(entry)
            page_num = entry.get("field_current", "?")
            records_count = entry.get("field_records_len", 0)
            first_title = entry.get("first_record_title", "")[:50]
            print(f"\n   🎯 Page {page_num} | {records_count} 条 | {first_title}")

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
    print("\n[4] 等待首页数据加载...")
    page.wait_for_timeout(5000)

    # 截图
    page.screenshot(path="/tmp/cde_page1.png")
    print("   截图: /tmp/cde_page1.png")

    # 记录首页数据
    initial_count = len(output["getDomesticGuideList_captured"])
    print(f"   已捕获 getDomesticGuideList: {initial_count} 次")

    # 查找分页元素
    print("\n[5] 查找分页元素...")
    pagination_info = page.evaluate("""() => {
        const results = [];
        
        // 查找所有可能的分页元素
        const selectors = [
            '.pagination', '.pager', '[class*="paging"]', '[class*="page"]',
            '.el-pagination', '.ant-pagination',
            'a[href*="page"]', 'button[class*="page"]',
            'li[class*="page"]', 'span[class*="page"]'
        ];
        
        for (const sel of selectors) {
            try {
                const els = document.querySelectorAll(sel);
                els.forEach(el => {
                    results.push({
                        selector: sel,
                        tag: el.tagName,
                        text: el.textContent.trim().substring(0, 50),
                        className: el.className,
                        visible: el.offsetParent !== null,
                        rect: el.getBoundingClientRect()
                    });
                });
            } catch(e) {}
        }
        
        return results;
    }""")
    
    print(f"   找到 {len(pagination_info)} 个分页相关元素")
    for info in pagination_info[:10]:
        print(f"      [{info['selector']}] <{info['tag']}> '{info['text']}' visible={info['visible']}")

    # 尝试翻页
    print("\n[6] 开始翻页测试...")
    
    # 策略1: 点击"下一页"按钮
    next_btn_selectors = [
        'a:has-text("下一页")',
        'button:has-text("下一页")',
        'a:has-text(">>")',
        'a:has-text(">")',
        'button:has-text(">")',
        '.next',
        '[class*="next"]',
        'a[title="下一页"]',
    ]
    
    clicked = False
    for sel in next_btn_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                print(f"   找到翻页按钮: {sel}")
                el.click()
                clicked = True
                break
        except Exception as e:
            continue
    
    if not clicked:
        # 策略2: 点击页码 2
        print("   尝试点击页码 2...")
        try:
            page.click('a:has-text("2"), button:has-text("2"), li:has-text("2")')
            clicked = True
        except:
            pass
    
    if not clicked:
        # 策略3: 使用 JavaScript 查找并点击
        print("   使用 JS 查找翻页按钮...")
        clicked = page.evaluate("""() => {
            // 查找包含"下一页"或">"的元素
            const allElements = document.querySelectorAll('a, button, li, span');
            for (const el of allElements) {
                const text = el.textContent.trim();
                if (text === '下一页' || text === '>' || text === '>>' || text === '2') {
                    if (el.offsetParent !== null) {
                        el.click();
                        return text;
                    }
                }
            }
            return null;
        }""")
        if clicked:
            print(f"   JS 点击: {clicked}")
    
    if clicked:
        print("   等待第 2 页数据加载...")
        page.wait_for_timeout(4000)
        page.screenshot(path="/tmp/cde_page2.png")
        print("   截图: /tmp/cde_page2.png")
        
        # 记录翻页事件
        new_count = len(output["getDomesticGuideList_captured"])
        if new_count > initial_count:
            output["pagination_events"].append({
                "action": "click_next",
                "from_page": 1,
                "to_page": 2,
                "new_responses": new_count - initial_count,
                "timestamp": datetime.now().isoformat()
            })
            print(f"   ✅ 翻页成功! 新增 {new_count - initial_count} 个响应")
        else:
            print(f"   ⚠️ 翻页后无新响应")
    
    # 再翻一页到第 3 页
    print("\n[7] 翻到第 3 页...")
    before_page3 = len(output["getDomesticGuideList_captured"])
    
    clicked = False
    for sel in next_btn_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                clicked = True
                break
        except:
            continue
    
    if not clicked:
        try:
            page.click('a:has-text("3"), button:has-text("3"), li:has-text("3")')
            clicked = True
        except:
            pass
    
    if clicked:
        print("   等待第 3 页数据加载...")
        page.wait_for_timeout(4000)
        page.screenshot(path="/tmp/cde_page3.png")
        print("   截图: /tmp/cde_page3.png")
        
        after_page3 = len(output["getDomesticGuideList_captured"])
        if after_page3 > before_page3:
            output["pagination_events"].append({
                "action": "click_next",
                "from_page": 2,
                "to_page": 3,
                "new_responses": after_page3 - before_page3,
                "timestamp": datetime.now().isoformat()
            })
            print(f"   ✅ 翻页成功! 新增 {after_page3 - before_page3} 个响应")
        else:
            print(f"   ⚠️ 翻页后无新响应")

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
    path = "/home/chenyingying/dazah/dazah-backend/scripts/regulatory_poc/cde_pagination_test.json"
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
    print("翻页测试报告")
    print(f"{'='*70}")
    print(f"  WAF 通过: {'✅' if output['waf_passed'] else '❌'}")
    print(f"  页面标题: {output['page_title']}")
    print(f"  总 XHR/Fetch: {len(output['all_xhr_fetch'])}")
    print(f"  getDomesticGuideList: {len(output['getDomesticGuideList_captured'])}")
    print(f"  翻页事件: {len(output['pagination_events'])}")

    if output["getDomesticGuideList_captured"]:
        print(f"\n  getDomesticGuideList 详情:")
        for i, cap in enumerate(output["getDomesticGuideList_captured"], 1):
            page_num = cap.get("field_current", "?")
            total = cap.get("field_total", "?")
            pages = cap.get("field_pages", "?")
            records = cap.get("field_records_len", 0)
            first_title = cap.get("first_record_title", "")[:60]
            
            print(f"\n  [{i}] 第 {page_num} 页 (共 {pages} 页, {total} 条)")
            print(f"      记录数: {records}")
            print(f"      首条: {first_title}")
            
            # 提取 MmEwMD 长度
            if "query_params" in cap and "MmEwMD" in cap["query_params"]:
                mmewmd = cap["query_params"]["MmEwMD"][0]
                print(f"      MmEwMD: {len(mmewmd)} 字符")

    if output["pagination_events"]:
        print(f"\n  翻页事件记录:")
        for event in output["pagination_events"]:
            print(f"      {event['from_page']} → {event['to_page']} | 新增 {event['new_responses']} 个响应")

    # 验证数据是否不同
    if len(output["getDomesticGuideList_captured"]) >= 2:
        titles = []
        for cap in output["getDomesticGuideList_captured"]:
            if cap.get("first_record_title"):
                titles.append(cap["first_record_title"])
        
        if len(set(titles)) == len(titles):
            print(f"\n  ✅ 数据验证: 各页首条记录不同，分页有效")
        else:
            print(f"\n  ⚠️ 数据验证: 存在重复的首条记录")

    print(f"\n  Cookies ({len(output['cookies'])} 个):")
    for c in output["cookies"][:5]:
        print(f"      {c['name']} @ {c['domain']} expires={c['expires_human']}")


if __name__ == "__main__":
    main()
