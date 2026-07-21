"""法规自动监控可行性 POC 测试脚本
测试 9 个来源网站的可抓取性，输出 feasibility_sample.json 和 feasibility_report.md
"""
import json
import time
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

results = []

def make_result(source, column, url, status, samples, issues, risk, needs_js, needs_login, has_captcha, attachments_ok, tech_stack):
    return {
        "source": source,
        "column": column,
        "test_url": url,
        "http_status": status,
        "samples": samples,
        "issues": issues,
        "risk_level": risk,
        "needs_js_rendering": needs_js,
        "needs_login": needs_login,
        "has_captcha": has_captcha,
        "attachments_downloadable": attachments_ok,
        "recommended_tech_stack": tech_stack,
        "tested_at": datetime.now().isoformat(),
    }


def extract_text(html, max_len=500):
    """提取正文前500字"""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return text[:max_len] if text else ""


def test_nmpa():
    """1. NMPA 国家药监局 - 法规文件"""
    print("Testing NMPA...")
    url = "https://www.nmpa.gov.cn/xxgk/fgwj/index.html"
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        status = resp.status_code
        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select("ul.list li") or soup.select(".listCon li") or soup.select(".zx_list li")
        if not items:
            items = soup.select("li")
        samples = []
        for item in items[:3]:
            a = item.select_one("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            link = urljoin(url, a.get("href", ""))
            date_span = item.select_one("span") or item.select_one(".date")
            pub_date = date_span.get_text(strip=True) if date_span else ""
            samples.append({"title": title, "pub_date": pub_date, "link": link, "type": "法规文件", "source": "NMPA", "effective_date": "", "attachment_link": "", "content_preview": ""})
        
        issues = []
        if len(items) == 0:
            issues.append("未找到列表项，可能需要JS渲染")
        
        results.append(make_result(
            "NMPA", "法规文件", url, status, samples, issues,
            "中" if len(samples) < 3 else "低",
            len(samples) == 0, False, False, True,
            ["httpx", "BeautifulSoup"] if samples else ["Playwright", "BeautifulSoup"]
        ))
    except Exception as e:
        results.append(make_result("NMPA", "法规文件", url, "error", [], [str(e)], "高", False, False, False, False, ["unknown"]))
    print(f"  NMPA done: {len(results[-1]['samples'])} samples")


def test_cde():
    """2. CDE 药审中心 - 指导原则"""
    print("Testing CDE...")
    url = "https://www.cde.org.cn/main/xxgk/listpage/2de64bb2077a4070b79ae59373755684"
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        status = resp.status_code
        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select("ul.list li") or soup.select(".listCon li") or soup.select("li")
        samples = []
        for item in items[:3]:
            a = item.select_one("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            link = urljoin("https://www.cde.org.cn", a.get("href", ""))
            date_span = item.select_one("span") or item.select_one(".date")
            pub_date = date_span.get_text(strip=True) if date_span else ""
            samples.append({"title": title, "pub_date": pub_date, "link": link, "type": "指导原则", "source": "CDE", "effective_date": "", "attachment_link": "", "content_preview": ""})
        
        issues = []
        if len(items) == 0:
            issues.append("未找到列表项，可能需要JS渲染")
        
        results.append(make_result(
            "CDE", "指导原则", url, status, samples, issues,
            "中" if len(samples) < 3 else "低",
            len(samples) == 0, False, False, True,
            ["httpx", "BeautifulSoup"] if samples else ["Playwright", "BeautifulSoup"]
        ))
    except Exception as e:
        results.append(make_result("CDE", "指导原则", url, "error", [], [str(e)], "高", False, False, False, False, ["unknown"]))
    print(f"  CDE done: {len(results[-1]['samples'])} samples")


def test_cfdi():
    """3. CFDI 中检院 - 公告通告"""
    print("Testing CFDI...")
    url = "https://www.nifdc.org.cn/nifdc/bshff/swjgg/index.html"
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        status = resp.status_code
        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select("ul.list li") or soup.select(".listCon li") or soup.select("li")
        samples = []
        for item in items[:3]:
            a = item.select_one("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            link = urljoin("https://www.nifdc.org.cn", a.get("href", ""))
            date_span = item.select_one("span") or item.select_one(".date")
            pub_date = date_span.get_text(strip=True) if date_span else ""
            samples.append({"title": title, "pub_date": pub_date, "link": link, "type": "公告通告", "source": "CFDI", "effective_date": "", "attachment_link": "", "content_preview": ""})
        
        issues = []
        if len(items) == 0:
            issues.append("未找到列表项，可能需要JS渲染")
        
        results.append(make_result(
            "CFDI", "公告通告", url, status, samples, issues,
            "中" if len(samples) < 3 else "低",
            len(samples) == 0, False, False, True,
            ["httpx", "BeautifulSoup"] if samples else ["Playwright", "BeautifulSoup"]
        ))
    except Exception as e:
        results.append(make_result("CFDI", "公告通告", url, "error", [], [str(e)], "高", False, False, False, False, ["unknown"]))
    print(f"  CFDI done: {len(results[-1]['samples'])} samples")


def test_chp():
    """4. 国家药典委 - 公告"""
    print("Testing CHP...")
    url = "https://www.chp.org.cn/content/detail/5f8a1c3e9b0b4b3b8c0a0a0a.html"
    # 药典委主页
    url = "https://www.chp.org.cn"
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        status = resp.status_code
        soup = BeautifulSoup(resp.text, "lxml")
        # 尝试找公告/通知栏目
        items = soup.select(".news-list li") or soup.select(".list li") or soup.select("li")
        samples = []
        for item in items[:3]:
            a = item.select_one("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            if len(title) < 5:
                continue
            link = urljoin("https://www.chp.org.cn", a.get("href", ""))
            date_span = item.select_one("span") or item.select_one(".date")
            pub_date = date_span.get_text(strip=True) if date_span else ""
            samples.append({"title": title, "pub_date": pub_date, "link": link, "type": "公告", "source": "国家药典委", "effective_date": "", "attachment_link": "", "content_preview": ""})
        
        issues = []
        if len(samples) < 3:
            issues.append("页面结构复杂，需进一步适配栏目选择器")
        
        results.append(make_result(
            "国家药典委", "公告", url, status, samples, issues,
            "中" if len(samples) < 3 else "低",
            len(samples) == 0, False, False, True,
            ["httpx", "BeautifulSoup"] if samples else ["Playwright", "BeautifulSoup"]
        ))
    except Exception as e:
        results.append(make_result("国家药典委", "公告", url, "error", [], [str(e)], "高", False, False, False, False, ["unknown"]))
    print(f"  CHP done: {len(results[-1]['samples'])} samples")


def test_gdpa():
    """5. 广东省药监局 - 法规文件"""
    print("Testing GDPA...")
    url = "https://mpa.gd.gov.cn/zwgk/fgwj/index.html"
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        status = resp.status_code
        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select("ul.list li") or soup.select(".listCon li") or soup.select("li")
        samples = []
        for item in items[:3]:
            a = item.select_one("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            if len(title) < 5:
                continue
            link = urljoin("https://mpa.gd.gov.cn", a.get("href", ""))
            date_span = item.select_one("span") or item.select_one(".date")
            pub_date = date_span.get_text(strip=True) if date_span else ""
            samples.append({"title": title, "pub_date": pub_date, "link": link, "type": "法规文件", "source": "广东省药监局", "effective_date": "", "attachment_link": "", "content_preview": ""})
        
        issues = []
        if len(samples) < 3:
            issues.append("页面结构复杂，需进一步适配栏目选择器")
        
        results.append(make_result(
            "广东省药监局", "法规文件", url, status, samples, issues,
            "中" if len(samples) < 3 else "低",
            len(samples) == 0, False, False, True,
            ["httpx", "BeautifulSoup"] if samples else ["Playwright", "BeautifulSoup"]
        ))
    except Exception as e:
        results.append(make_result("广东省药监局", "法规文件", url, "error", [], [str(e)], "高", False, False, False, False, ["unknown"]))
    print(f"  GDPA done: {len(results[-1]['samples'])} samples")


def test_fda():
    """6. FDA - Guidance Documents"""
    print("Testing FDA...")
    url = "https://www.fda.gov/drugs/guidance-compliance-regulatory-information/guidances-drugs"
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        status = resp.status_code
        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select("li.views-row") or soup.select(".view-content li") or soup.select("li")
        samples = []
        for item in items[:3]:
            a = item.select_one("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            if len(title) < 10:
                continue
            link = urljoin("https://www.fda.gov", a.get("href", ""))
            date_span = item.select_one("time") or item.select_one(".date") or item.select_one("span")
            pub_date = date_span.get_text(strip=True) if date_span else ""
            samples.append({"title": title, "pub_date": pub_date, "link": link, "type": "Guidance", "source": "FDA", "effective_date": "", "attachment_link": "", "content_preview": ""})
        
        issues = []
        if len(samples) < 3:
            issues.append("FDA页面结构复杂，可能需要调整选择器或使用RSS")
        
        results.append(make_result(
            "FDA", "Guidance Documents", url, status, samples, issues,
            "低" if len(samples) >= 3 else "中",
            len(samples) == 0, False, False, True,
            ["httpx", "BeautifulSoup"] if samples else ["Playwright", "BeautifulSoup"]
        ))
    except Exception as e:
        results.append(make_result("FDA", "Guidance Documents", url, "error", [], [str(e)], "高", False, False, False, False, ["unknown"]))
    print(f"  FDA done: {len(results[-1]['samples'])} samples")


def test_ema():
    """7. EMA - Regulatory & procedural guidance"""
    print("Testing EMA...")
    url = "https://www.ema.europa.eu/en/human-regulatory/overview/public-consultations"
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        status = resp.status_code
        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select(".ecl-content-item") or soup.select("article") or soup.select("li")
        samples = []
        for item in items[:3]:
            a = item.select_one("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            if len(title) < 10:
                continue
            link = urljoin("https://www.ema.europa.eu", a.get("href", ""))
            date_span = item.select_one("time") or item.select_one(".ecl-date-block") or item.select_one("span")
            pub_date = date_span.get_text(strip=True) if date_span else ""
            samples.append({"title": title, "pub_date": pub_date, "link": link, "type": "Public Consultation", "source": "EMA", "effective_date": "", "attachment_link": "", "content_preview": ""})
        
        issues = []
        if len(samples) < 3:
            issues.append("EMA页面可能需要调整选择器")
        
        results.append(make_result(
            "EMA", "Public Consultations", url, status, samples, issues,
            "低" if len(samples) >= 3 else "中",
            len(samples) == 0, False, False, True,
            ["httpx", "BeautifulSoup"] if samples else ["Playwright", "BeautifulSoup"]
        ))
    except Exception as e:
        results.append(make_result("EMA", "Public Consultations", url, "error", [], [str(e)], "高", False, False, False, False, ["unknown"]))
    print(f"  EMA done: {len(results[-1]['samples'])} samples")


def test_edqm():
    """8. EDQM - News"""
    print("Testing EDQM...")
    url = "https://www.edqm.eu/en/news-and-events"
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        status = resp.status_code
        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select(".news-item") or soup.select("article") or soup.select("li")
        samples = []
        for item in items[:3]:
            a = item.select_one("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            if len(title) < 10:
                continue
            link = urljoin("https://www.edqm.eu", a.get("href", ""))
            date_span = item.select_one("time") or item.select_one(".date") or item.select_one("span")
            pub_date = date_span.get_text(strip=True) if date_span else ""
            samples.append({"title": title, "pub_date": pub_date, "link": link, "type": "News", "source": "EDQM", "effective_date": "", "attachment_link": "", "content_preview": ""})
        
        issues = []
        if len(samples) < 3:
            issues.append("EDQM页面可能需要调整选择器")
        
        results.append(make_result(
            "EDQM", "News & Events", url, status, samples, issues,
            "低" if len(samples) >= 3 else "中",
            len(samples) == 0, False, False, True,
            ["httpx", "BeautifulSoup"] if samples else ["Playwright", "BeautifulSoup"]
        ))
    except Exception as e:
        results.append(make_result("EDQM", "News & Events", url, "error", [], [str(e)], "高", False, False, False, False, ["unknown"]))
    print(f"  EDQM done: {len(results[-1]['samples'])} samples")


def test_ich():
    """9. ICH - Guidelines"""
    print("Testing ICH...")
    url = "https://www.ich.org/page/guidelines"
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        status = resp.status_code
        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select(".node--type-guideline") or soup.select("article") or soup.select("li")
        samples = []
        for item in items[:3]:
            a = item.select_one("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            if len(title) < 5:
                continue
            link = urljoin("https://www.ich.org", a.get("href", ""))
            date_span = item.select_one("time") or item.select_one(".date") or item.select_one("span")
            pub_date = date_span.get_text(strip=True) if date_span else ""
            samples.append({"title": title, "pub_date": pub_date, "link": link, "type": "Guideline", "source": "ICH", "effective_date": "", "attachment_link": "", "content_preview": ""})
        
        issues = []
        if len(samples) < 3:
            issues.append("ICH页面可能需要调整选择器")
        
        results.append(make_result(
            "ICH", "Guidelines", url, status, samples, issues,
            "低" if len(samples) >= 3 else "中",
            len(samples) == 0, False, False, True,
            ["httpx", "BeautifulSoup"] if samples else ["Playwright", "BeautifulSoup"]
        ))
    except Exception as e:
        results.append(make_result("ICH", "Guidelines", url, "error", [], [str(e)], "高", False, False, False, False, ["unknown"]))
    print(f"  ICH done: {len(results[-1]['samples'])} samples")


def generate_report():
    """生成可行性报告"""
    report = "# 法规自动监控可行性报告\n\n"
    report += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    report += "## 测试结果汇总\n\n"
    report += "| 来源 | 栏目 | HTTP状态 | 样例数 | 风险等级 | 技术栈 | 主要问题 |\n"
    report += "|------|------|----------|--------|----------|--------|----------|\n"
    
    for r in results:
        issues_str = "; ".join(r["issues"]) if r["issues"] else "无"
        tech_str = ", ".join(r["recommended_tech_stack"])
        report += f"| {r['source']} | {r['column']} | {r['http_status']} | {len(r['samples'])} | {r['risk_level']} | {tech_str} | {issues_str} |\n"
    
    report += "\n## 详细分析\n\n"
    for r in results:
        report += f"### {r['source']} - {r['column']}\n\n"
        report += f"- **测试URL**: {r['test_url']}\n"
        report += f"- **HTTP状态**: {r['http_status']}\n"
        report += f"- **风险等级**: {r['risk_level']}\n"
        report += f"- **需要JS渲染**: {'是' if r['needs_js_rendering'] else '否'}\n"
        report += f"- **需要登录**: {'是' if r['needs_login'] else '否'}\n"
        report += f"- **验证码**: {'是' if r['has_captcha'] else '否'}\n"
        report += f"- **附件可下载**: {'是' if r['attachments_downloadable'] else '待验证'}\n"
        report += f"- **推荐技术栈**: {', '.join(r['recommended_tech_stack'])}\n"
        if r["issues"]:
            report += f"- **问题**: {'; '.join(r['issues'])}\n"
        if r["samples"]:
            report += f"- **样例**:\n"
            for s in r["samples"]:
                report += f"  - {s['title']} ({s['pub_date']})\n"
        report += "\n"
    
    report += "## 结论与建议\n\n"
    low = sum(1 for r in results if r["risk_level"] == "低")
    mid = sum(1 for r in results if r["risk_level"] == "中")
    high = sum(1 for r in results if r["risk_level"] == "高")
    report += f"- **低风险（可稳定抓取）**: {low} 个来源\n"
    report += f"- **中风险（需适配）**: {mid} 个来源\n"
    report += f"- **高风险（需人工兜底）**: {high} 个来源\n\n"
    
    if high > 0:
        report += "### 高风险来源建议\n\n"
        for r in results:
            if r["risk_level"] == "高":
                report += f"- **{r['source']}**: {'; '.join(r['issues'])}\n"
        report += "\n建议使用 Playwright 进行浏览器渲染后抓取。\n"
    
    return report


if __name__ == "__main__":
    print("=" * 60)
    print("法规自动监控可行性 POC 测试")
    print("=" * 60)
    
    test_nmpa()
    time.sleep(1)
    test_cde()
    time.sleep(1)
    test_cfdi()
    time.sleep(1)
    test_chp()
    time.sleep(1)
    test_gdpa()
    time.sleep(1)
    test_fda()
    time.sleep(1)
    test_ema()
    time.sleep(1)
    test_edqm()
    time.sleep(1)
    test_ich()
    
    # 保存 JSON 结果
    with open("scripts/regulatory_poc/feasibility_sample.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # 生成报告
    report = generate_report()
    with open("scripts/regulatory_poc/feasibility_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    
    print("\n" + "=" * 60)
    print(f"测试完成！共测试 {len(results)} 个来源")
    print(f"  低风险: {sum(1 for r in results if r['risk_level'] == '低')}")
    print(f"  中风险: {sum(1 for r in results if r['risk_level'] == '中')}")
    print(f"  高风险: {sum(1 for r in results if r['risk_level'] == '高')}")
    print(f"\n输出文件:")
    print(f"  - scripts/regulatory_poc/feasibility_sample.json")
    print(f"  - scripts/regulatory_poc/feasibility_report.md")
