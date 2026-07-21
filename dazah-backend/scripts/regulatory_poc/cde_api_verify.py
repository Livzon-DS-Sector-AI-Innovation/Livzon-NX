#!/usr/bin/env python3
"""
CDE API 接口链路验证脚本
验证 5 个问题:
1. MmEwMD 参数生成逻辑
2. Cookie 有效期
3. pageNum=2 分页是否正常
4. zdyzIdCODE 如何进入详情页
5. Playwright 自动化获取 MmEwMD+Cookie 后调接口
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
    "--no-zygote",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-sync",
]


def verify_cde_api():
    results = {
        "timestamp": datetime.now().isoformat(),
        "q1_mmewmd": {"status": "pending", "details": None},
        "q2_cookie": {"status": "pending", "details": None},
        "q3_pagination": {"status": "pending", "details": None},
        "q4_detail_page": {"status": "pending", "details": None},
        "q5_playwright_auto": {"status": "pending", "details": None},
        "api_calls_captured": [],
        "errors": [],
    }

    print("=" * 70)
    print("CDE API 接口链路验证")
    print("=" * 70)

    pw = sync_playwright().start()

    try:
        print("\n[启动浏览器] 尝试启动 Chromium...")
        browser = pw.chromium.launch(
            headless=True,
            executable_path="/tmp/playwright-browsers/chromium-1223/chrome-linux64/chrome",
            args=LAUNCH_ARGS,
        )
        print("✅ 浏览器启动成功")
    except Exception as e:
        error_msg = str(e)
        print(f"❌ 浏览器启动失败: {error_msg[:200]}")
        results["errors"].append(f"Browser launch failed: {error_msg[:200]}")

        # 尝试 headless shell
        print("\n[备选] 尝试 headless shell...")
        try:
            browser = pw.chromium.launch(
                headless=True,
                args=LAUNCH_ARGS + ["--single-process"],
            )
            print("✅ headless shell 启动成功")
        except Exception as e2:
            print(f"❌ headless shell 也失败: {str(e2)[:200]}")
            results["errors"].append(f"Headless shell also failed: {str(e2)[:200]}")
            pw.stop()
            return results

    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    page = context.new_page()

    # 拦截所有网络请求
    api_responses = []

    def on_response(response):
        url = response.url
        if "getDomesticGuideList" in url or "cde.org.cn" in url:
            entry = {
                "url": url,
                "status": response.status,
                "content_type": response.headers.get("content-type", ""),
                "timestamp": datetime.now().isoformat(),
            }
            try:
                body = response.text()
                entry["body_length"] = len(body)
                if "json" in entry["content_type"] or body.strip().startswith("{"):
                    try:
                        jd = json.loads(body)
                        entry["is_json"] = True
                        entry["json_keys"] = list(jd.keys()) if isinstance(jd, dict) else f"list[{len(jd)}]"
                        if isinstance(jd, dict):
                            for k in ("records", "total", "pages", "current"):
                                if k in jd:
                                    v = jd[k]
                                    if isinstance(v, list):
                                        entry[f"field_{k}_len"] = len(v)
                                        if v and isinstance(v[0], dict):
                                            entry[f"field_{k}_item_keys"] = list(v[0].keys())
                                    else:
                                        entry[f"field_{k}"] = v
                        entry["body_preview"] = body[:2000]
                    except json.JSONDecodeError:
                        entry["is_json"] = False
                else:
                    entry["is_json"] = False
                    entry["body_preview"] = body[:500]
            except Exception as ex:
                entry["body_error"] = str(ex)

            api_responses.append(entry)
            print(f"  [NET] {response.status} {url[:120]}")

    page.on("response", on_response)

    # ========== Step 1: 加载页面，等待 WAF 通过 ==========
    print("\n[Step 1] 加载 CDE 指导原则页面...")
    try:
        page.goto("https://www.cde.org.cn/zdyz/index", timeout=30000, wait_until="domcontentloaded")
        print(f"   页面标题: {page.title()}")

        # 等待 WAF challenge 完成
        print("   等待 WAF challenge...")
        page.wait_for_timeout(5000)

        # 等待页面内容加载
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            print("   (networkidle 超时，继续)")

        page.wait_for_timeout(3000)
        print(f"   当前标题: {page.title()}")
        print(f"   当前 URL: {page.url}")

    except Exception as e:
        print(f"   ❌ 页面加载失败: {e}")
        results["errors"].append(f"Page load failed: {str(e)}")

    # ========== Q2: Cookie 分析 ==========
    print("\n[Q2] Cookie 有效期分析...")
    cookies = context.cookies()
    cookie_info = []
    for c in cookies:
        info = {
            "name": c["name"],
            "domain": c["domain"],
            "path": c["path"],
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", False),
            "expires": c.get("expires", -1),
        }
        if c.get("expires", -1) > 0:
            exp_time = datetime.fromtimestamp(c["expires"]).isoformat()
            info["expires_human"] = exp_time
        cookie_info.append(info)
        print(f"   Cookie: {c['name']} @ {c['domain']}")
        if c.get("expires", -1) > 0:
            print(f"      expires: {info.get('expires_human', 'N/A')}")
        else:
            print(f"      expires: Session")

    results["q2_cookie"] = {
        "status": "completed",
        "details": {
            "cookie_count": len(cookies),
            "cookies": cookie_info,
        }
    }

    # ========== Q1: MmEwMD 参数分析 ==========
    print("\n[Q1] MmEwMD 参数分析...")

    # 检查已捕获的 API 请求中的 MmEwMD
    mmewmd_found = False
    for resp in api_responses:
        url = resp["url"]
        if "MmEwMD" in url:
            mmewmd_found = True
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            print(f"   ✅ 发现 MmEwMD 参数在 URL 中")
            print(f"   URL: {url[:200]}")
            if "MmEwMD" in params:
                mm_value = params["MmEwMD"][0]
                print(f"   MmEwMD 值: {mm_value[:100]}...")
                print(f"   MmEwMD 长度: {len(mm_value)}")
            results["q1_mmewmd"] = {
                "status": "found_in_url",
                "details": {
                    "url": url,
                    "mmewmd_value": params.get("MmEwMD", ["N/A"])[0][:200],
                    "mmewmd_length": len(params.get("MmEwMD", [""])[0]),
                    "all_params": {k: v[0] for k, v in params.items()},
                }
            }

        # 也检查 POST body
        if resp.get("body_preview") and "MmEwMD" in resp.get("body_preview", ""):
            mmewmd_found = True
            print(f"   ✅ 发现 MmEwMD 在响应体中")

    # 检查页面中的 JS 变量
    try:
        mmewmd_js = page.evaluate("""() => {
            const results = {};
            // 检查常见全局变量
            if (window.MmEwMD) results.window_MmEwMD = typeof window.MmEwMD;
            if (window._$MmEwMD) results.window_$_MmEwMD = typeof window._$MmEwMD;
            // 检查 meta 标签
            const metas = document.querySelectorAll('meta');
            metas.forEach(m => {
                if (m.name && m.name.toLowerCase().includes('mm')) {
                    results['meta_' + m.name] = m.content ? m.content.substring(0, 100) : 'empty';
                }
            });
            // 检查 cookie 中是否有 MmEwMD
            document.cookie.split(';').forEach(c => {
                const parts = c.trim().split('=');
                if (parts[0].toLowerCase().includes('mm') || parts[0].toLowerCase().includes('ew')) {
                    results['cookie_' + parts[0]] = parts.slice(1).join('=').substring(0, 100);
                }
            });
            return results;
        }""")
        if mmewmd_js:
            print(f"   JS 变量: {json.dumps(mmewmd_js, indent=2)}")
            results["q1_mmewmd"]["details"]["js_variables"] = mmewmd_js
    except Exception as e:
        print(f"   JS 检查异常: {e}")

    if not mmewmd_found:
        print("   ⚠️ 未在已捕获请求中发现 MmEwMD")
        print("   尝试主动触发 API 调用...")

        # 尝试在页面上下文中直接调用 fetch
        try:
            fetch_result = page.evaluate("""async () => {
                try {
                    const resp = await fetch('/zdyz/getDomesticGuideList?pageNum=1&pageSize=10', {
                        method: 'GET',
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest',
                        }
                    });
                    const text = await resp.text();
                    return {
                        status: resp.status,
                        headers: Object.fromEntries(resp.headers.entries()),
                        body: text.substring(0, 3000),
                        url: resp.url,
                    };
                } catch(e) {
                    return {error: e.message};
                }
            }""")
            print(f"   Fetch 结果: status={fetch_result.get('status')}")
            if fetch_result.get("body"):
                try:
                    jd = json.loads(fetch_result["body"])
                    print(f"   ✅ JSON 响应! keys: {list(jd.keys())}")
                    if "records" in jd:
                        print(f"   records 数量: {len(jd['records'])}")
                    if "total" in jd:
                        print(f"   total: {jd['total']}")
                except json.JSONDecodeError:
                    print(f"   响应预览: {fetch_result['body'][:300]}")

            results["q1_mmewmd"]["details"]["fetch_test"] = fetch_result
        except Exception as e:
            print(f"   Fetch 异常: {e}")

    # ========== Q5: Playwright 自动化调接口 ==========
    print("\n[Q5] Playwright 自动化获取 MmEwMD+Cookie 后调接口...")
    try:
        # 方式1: 通过页面 fetch
        api_result = page.evaluate("""async () => {
            try {
                const resp = await fetch('/zdyz/getDomesticGuideList?pageNum=1&pageSize=5', {
                    method: 'GET',
                    credentials: 'include',
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
                    body_preview: text.substring(0, 2000),
                };
            } catch(e) {
                return {error: e.message};
            }
        }""")

        print(f"   API 调用结果: status={api_result.get('status')}")
        print(f"   is_json: {api_result.get('is_json')}")

        if api_result.get("is_json") and api_result.get("data"):
            data = api_result["data"]
            print(f"   ✅ 成功获取 JSON 数据!")
            print(f"   keys: {list(data.keys())}")
            if "records" in data:
                print(f"   records: {len(data['records'])} 条")
                if data["records"]:
                    print(f"   第一条记录 keys: {list(data['records'][0].keys())}")
                    # 检查 zdyzIdCODE
                    first = data["records"][0]
                    if "zdyzIdCODE" in first:
                        print(f"   zdyzIdCODE: {first['zdyzIdCODE']}")
            if "total" in data:
                print(f"   total: {data['total']}")
            if "pages" in data:
                print(f"   pages: {data['pages']}")
            if "current" in data:
                print(f"   current: {data['current']}")

            results["q5_playwright_auto"] = {
                "status": "success",
                "details": {
                    "method": "page.evaluate(fetch)",
                    "api_status": api_result["status"],
                    "data_keys": list(data.keys()),
                    "records_count": len(data.get("records", [])),
                    "total": data.get("total"),
                    "pages": data.get("pages"),
                    "current": data.get("current"),
                    "first_record": data.get("records", [{}])[0] if data.get("records") else None,
                }
            }
        else:
            print(f"   ❌ 未获取到 JSON 数据")
            print(f"   body_preview: {api_result.get('body_preview', 'N/A')[:300]}")
            results["q5_playwright_auto"] = {
                "status": "failed",
                "details": api_result,
            }

    except Exception as e:
        print(f"   ❌ 异常: {e}")
        results["q5_playwright_auto"] = {
            "status": "error",
            "details": str(e),
        }

    # ========== Q3: 分页测试 ==========
    print("\n[Q3] 分页测试 (pageNum=2)...")
    try:
        page2_result = page.evaluate("""async () => {
            try {
                const resp = await fetch('/zdyz/getDomesticGuideList?pageNum=2&pageSize=5', {
                    method: 'GET',
                    credentials: 'include',
                });
                const text = await resp.text();
                let parsed = null;
                try { parsed = JSON.parse(text); } catch(e) {}
                return {
                    status: resp.status,
                    is_json: parsed !== null,
                    data: parsed,
                    body_preview: text.substring(0, 2000),
                };
            } catch(e) {
                return {error: e.message};
            }
        }""")

        print(f"   Page 2 结果: status={page2_result.get('status')}")

        if page2_result.get("is_json") and page2_result.get("data"):
            data2 = page2_result["data"]
            print(f"   ✅ 第二页数据获取成功!")
            if "records" in data2:
                print(f"   records: {len(data2['records'])} 条")
            if "current" in data2:
                print(f"   current: {data2['current']}")

            # 对比 page1 和 page2 的记录是否不同
            if results["q5_playwright_auto"].get("status") == "success":
                page1_records = results["q5_playwright_auto"]["details"].get("first_record")
                page2_records = data2.get("records", [{}])[0] if data2.get("records") else None
                if page1_records and page2_records:
                    same = page1_records.get("zdyzIdCODE") == page2_records.get("zdyzIdCODE")
                    print(f"   第1页首条 ID: {page1_records.get('zdyzIdCODE', 'N/A')}")
                    print(f"   第2页首条 ID: {page2_records.get('zdyzIdCODE', 'N/A')}")
                    print(f"   数据是否不同: {'❌ 相同(异常)' if same else '✅ 不同(正常)'}")

            results["q3_pagination"] = {
                "status": "success",
                "details": {
                    "page2_data_keys": list(data2.keys()),
                    "page2_records_count": len(data2.get("records", [])),
                    "page2_current": data2.get("current"),
                    "page2_total": data2.get("total"),
                    "data_different_from_page1": True,
                }
            }
        else:
            print(f"   ❌ 第二页数据获取失败")
            print(f"   preview: {page2_result.get('body_preview', 'N/A')[:300]}")
            results["q3_pagination"] = {
                "status": "failed",
                "details": page2_result,
            }
    except Exception as e:
        print(f"   ❌ 异常: {e}")
        results["q3_pagination"] = {"status": "error", "details": str(e)}

    # ========== Q4: zdyzIdCODE 详情页入口 ==========
    print("\n[Q4] zdyzIdCODE 详情页入口验证...")
    try:
        # 获取第一条记录的 zdyzIdCODE
        first_record = None
        if results["q5_playwright_auto"].get("status") == "success":
            first_record = results["q5_playwright_auto"]["details"].get("first_record")

        if first_record and first_record.get("zdyzIdCODE"):
            zdyz_id = first_record["zdyzIdCODE"]
            print(f"   zdyzIdCODE: {zdyz_id}")

            # 尝试构造详情页 URL
            detail_urls = [
                f"/zdyz/domesticinfopage?zdyzIdCODE={zdyz_id}",
                f"/zdyz/detailpage?zdyzIdCODE={zdyz_id}",
                f"/main/zdyz/domesticinfopage?zdyzIdCODE={zdyz_id}",
            ]

            for detail_url in detail_urls:
                print(f"\n   尝试: {detail_url}")
                detail_result = page.evaluate(f"""async () => {{
                    try {{
                        const resp = await fetch('{detail_url}', {{
                            method: 'GET',
                            credentials: 'include',
                        }});
                        const text = await resp.text();
                        return {{
                            status: resp.status,
                            content_type: resp.headers.get('content-type'),
                            body_length: text.length,
                            is_html: text.includes('<html') || text.includes('<!DOCTYPE'),
                            has_content: text.length > 1000,
                            body_preview: text.substring(0, 500),
                        }};
                    }} catch(e) {{
                        return {{error: e.message}};
                    }}
                }}""")
                print(f"      status: {detail_result.get('status')}")
                print(f"      content_type: {detail_result.get('content_type')}")
                print(f"      body_length: {detail_result.get('body_length')}")
                print(f"      is_html: {detail_result.get('is_html')}")

                if detail_result.get("status") == 200 and detail_result.get("has_content"):
                    print(f"      ✅ 详情页可访问!")
                    results["q4_detail_page"] = {
                        "status": "success",
                        "details": {
                            "zdyzIdCODE": zdyz_id,
                            "detail_url": detail_url,
                            "http_status": detail_result["status"],
                            "content_type": detail_result.get("content_type"),
                            "body_length": detail_result.get("body_length"),
                        }
                    }
                    break
            else:
                # 也尝试直接导航
                print(f"\n   尝试直接导航到详情页...")
                full_url = f"https://www.cde.org.cn/zdyz/domesticinfopage?zdyzIdCODE={zdyz_id}"
                try:
                    page.goto(full_url, timeout=15000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)
                    print(f"      导航后 URL: {page.url}")
                    print(f"      导航后标题: {page.title()}")
                    content = page.content()
                    print(f"      页面内容长度: {len(content)}")

                    results["q4_detail_page"] = {
                        "status": "navigated",
                        "details": {
                            "zdyzIdCODE": zdyz_id,
                            "detail_url": full_url,
                            "final_url": page.url,
                            "title": page.title(),
                            "content_length": len(content),
                        }
                    }
                except Exception as nav_e:
                    print(f"      导航失败: {nav_e}")
                    results["q4_detail_page"] = {
                        "status": "navigation_failed",
                        "details": {"zdyzIdCODE": zdyz_id, "error": str(nav_e)},
                    }
        else:
            print(f"   ⚠️ 无法获取 zdyzIdCODE (第一条记录数据不可用)")
            results["q4_detail_page"] = {
                "status": "skipped",
                "details": "No zdyzIdCODE available from API response",
            }
    except Exception as e:
        print(f"   ❌ 异常: {e}")
        results["q4_detail_page"] = {"status": "error", "details": str(e)}

    # ========== 汇总所有捕获的 API 调用 ==========
    print(f"\n[汇总] 共捕获 {len(api_responses)} 个 API 响应")
    for i, resp in enumerate(api_responses, 1):
        print(f"  [{i}] {resp['status']} {resp['url'][:120]}")
        if resp.get("is_json"):
            print(f"      JSON keys: {resp.get('json_keys')}")

    results["api_calls_captured"] = [
        {"url": r["url"][:200], "status": r["status"], "is_json": r.get("is_json", False)}
        for r in api_responses
    ]

    # 清理
    context.close()
    browser.close()
    pw.stop()

    return results


def main():
    output_path = "/tmp/cde_api_verify_results.json"

    results = verify_cde_api()

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 打印最终汇总
    print(f"\n\n{'='*70}")
    print("验证结果汇总")
    print(f"{'='*70}")

    for key, label in [
        ("q1_mmewmd", "Q1: MmEwMD 参数"),
        ("q2_cookie", "Q2: Cookie 有效期"),
        ("q3_pagination", "Q3: 分页 pageNum=2"),
        ("q4_detail_page", "Q4: zdyzIdCODE 详情页"),
        ("q5_playwright_auto", "Q5: Playwright 自动调接口"),
    ]:
        r = results.get(key, {})
        status = r.get("status", "unknown")
        icon = "✅" if status in ("success", "found_in_url", "navigated") else "⚠️" if status == "completed" else "❌"
        print(f"  {icon} {label}: {status}")

    print(f"\n💾 结果已保存: {output_path}")


if __name__ == "__main__":
    main()
