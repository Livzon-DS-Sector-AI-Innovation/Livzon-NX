"""CDE 国内药品技术指导原则采集适配器。

核心原则：
- 不手动构造 MmEwMD
- 不缓存 MmEwMD
- 不直接 requests 硬调接口
- 使用 Playwright 打开页面
- 监听页面自身触发的 getDomesticGuideList 响应
- 翻页通过页面操作触发
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# 浏览器配置（通过环境变量覆盖，默认使用 Playwright 标准安装路径）
CRAWLER_HEADLESS = os.getenv("CRAWLER_HEADLESS", "true").lower() == "true"
CRAWLER_BROWSERS_PATH = os.getenv("CRAWLER_BROWSERS_PATH", "")  # 空字符串 = Playwright 默认路径

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
const origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (p) => (
    p.name === 'notifications' ? Promise.resolve({state: Notification.permission}) : origQuery(p)
);
"""

# CDE 国内药品技术指导原则列表页 URL
CDE_GUIDELINE_LIST_URL = "https://www.cde.org.cn/zdyz/listpage/9cd8db3b7530c6fa0c86485e563f93c7"

# 详情页 URL 模板
CDE_DETAIL_URL_TEMPLATE = "https://www.cde.org.cn/zdyz/domesticinfopage?zdyzIdCODE={zdyzIdCODE}"


class CdeDomesticGuidelineAdapter:
    """CDE 国内药品技术指导原则采集适配器。

    使用 Playwright 页面驱动模式：
    1. 打开列表页
    2. 监听页面自身触发的 getDomesticGuideList 响应
    3. 通过点击分页按钮触发翻页
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.list_url = CDE_GUIDELINE_LIST_URL
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    async def start(self):
        """启动浏览器"""
        if CRAWLER_BROWSERS_PATH:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = CRAWLER_BROWSERS_PATH

        self._pw = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {
            "headless": self.headless,
            "args": LAUNCH_ARGS,
            "ignore_default_args": ["--enable-automation"],
        }
        self._browser = await self._pw.chromium.launch(**launch_kwargs)
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        await self._context.add_init_script(STEALTH_JS)
        self._page = await self._context.new_page()
        logger.info("浏览器启动成功")

    async def stop(self):
        """关闭浏览器"""
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception as e:
            logger.warning(f"关闭浏览器时出错: {e}")
        finally:
            self._context = None
            self._browser = None
            self._pw = None
            self._page = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()

    def _parse_guide_list_response(self, url: str, body: str) -> dict | None:
        """解析 getDomesticGuideList 响应，返回解析后的数据或 None"""
        if "getDomesticGuideList" not in url:
            return None

        try:
            if not body.strip().startswith("{"):
                return None
            data = json.loads(body)
        except Exception as e:
            logger.warning(f"解析响应失败: {e}")
            return None

        if data.get("code") != 200:
            logger.warning(f"API 返回非 200: code={data.get('code')}, msg={data.get('msg')}")
            return None

        response_data = data.get("data", {})
        if not isinstance(response_data, dict):
            return None

        records = response_data.get("records", [])
        total = response_data.get("total", 0)
        pages = response_data.get("pages", 0)
        current = response_data.get("current", 0)

        # 从 URL 解析页码
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        page_num = int(params.get("pageNum", [0])[0])

        return {
            "page_num": page_num,
            "records": records,
            "total": total,
            "pages": pages,
            "current": current,
            "success": True,
        }

    async def _open_page_and_wait_for_first_response(self, timeout_ms: int = 30000) -> dict | None:
        """打开列表页并等待第一次 getDomesticGuideList 响应"""
        captured = {"result": None}
        event = asyncio.Event()

        async def on_response(response):
            url = response.url
            if "cde.org.cn" not in url:
                return
            if "getDomesticGuideList" not in url:
                return
            try:
                body = await response.text()
                result = self._parse_guide_list_response(url, body)
                if result:
                    captured["result"] = result
                    event.set()
            except Exception as e:
                logger.warning(f"处理响应失败: {e}")

        self._page.on("response", on_response)

        try:
            await self._page.goto(self.list_url, wait_until="networkidle", timeout=timeout_ms)
            # 等待响应被捕获
            try:
                await asyncio.wait_for(event.wait(), timeout=timeout_ms / 1000)
            except asyncio.TimeoutError:
                logger.warning("等待 getDomesticGuideList 响应超时")
        finally:
            self._page.remove_listener("response", on_response)

        return captured["result"]

    async def _click_next_page_and_capture(self, timeout_ms: int = 15000) -> dict | None:
        """点击下一页按钮并捕获响应"""
        captured = {"result": None}
        event = asyncio.Event()

        async def on_response(response):
            url = response.url
            if "cde.org.cn" not in url:
                return
            if "getDomesticGuideList" not in url:
                return
            try:
                body = await response.text()
                result = self._parse_guide_list_response(url, body)
                if result:
                    captured["result"] = result
                    event.set()
            except Exception as e:
                logger.warning(f"处理响应失败: {e}")

        self._page.on("response", on_response)

        try:
            # 尝试多种选择器点击下一页
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
            
            clicked = False
            for sel in next_btn_selectors:
                try:
                    el = self._page.locator(sel)
                    if await el.count() > 0 and await el.first.is_visible():
                        await el.first.click()
                        clicked = True
                        logger.info(f"点击翻页按钮: {sel}")
                        break
                except Exception:
                    continue
            
            if not clicked:
                # 尝试通过 JS 点击
                clicked_text = await self._page.evaluate("""() => {
                    const btns = document.querySelectorAll('a, button, li');
                    for (const b of btns) {
                        const text = b.textContent.trim();
                        if (text === '下一页' || text === '>' || text === '›' || text === '>>') {
                            b.click();
                            return text;
                        }
                    }
                    return null;
                }""")
                if clicked_text:
                    clicked = True
                    logger.info(f"JS 点击翻页: {clicked_text}")
            
            if not clicked:
                logger.warning("未找到下一页按钮")
                return None

            # 等待响应
            try:
                await asyncio.wait_for(event.wait(), timeout=timeout_ms / 1000)
            except asyncio.TimeoutError:
                logger.warning("翻页等待响应超时")
        finally:
            self._page.remove_listener("response", on_response)

        return captured["result"]

    async def sync_page(self, page_num: int = 1) -> dict[str, Any]:
        """同步指定页数据。

        Args:
            page_num: 页码（从 1 开始）

        Returns:
            {
                "page_num": int,
                "records": list[dict],
                "total": int,
                "pages": int,
                "success": bool,
                "error": str | None,
            }
        """
        if page_num < 1:
            return {"page_num": page_num, "records": [], "total": 0, "pages": 0,
                    "success": False, "error": "页码必须 >= 1"}

        try:
            # 第一页：直接打开页面
            if page_num == 1:
                result = await self._open_page_and_wait_for_first_response()
                if not result:
                    return {"page_num": 1, "records": [], "total": 0, "pages": 0,
                            "success": False, "error": "未捕获到 getDomesticGuideList 响应"}
                return {**result, "error": None}

            # 非第一页：先打开页面到第 1 页，然后翻页
            first_result = await self._open_page_and_wait_for_first_response()
            if not first_result:
                return {"page_num": page_num, "records": [], "total": 0, "pages": 0,
                        "success": False, "error": "打开页面失败"}

            # 翻到目标页
            current_page = 1
            target_result = None
            max_flips = page_num - 1

            for _ in range(max_flips):
                await asyncio.sleep(1)  # 避免请求过快
                result = await self._click_next_page_and_capture()
                if not result:
                    return {"page_num": page_num, "records": [], "total": 0, "pages": 0,
                            "success": False, "error": f"翻页到第 {current_page + 1} 页失败"}
                current_page += 1
                if current_page == page_num:
                    target_result = result
                    break

            if not target_result:
                return {"page_num": page_num, "records": [], "total": 0, "pages": 0,
                        "success": False, "error": f"翻页到第 {page_num} 页失败"}

            return {**target_result, "error": None}

        except Exception as e:
            logger.exception(f"同步第 {page_num} 页异常")
            return {"page_num": page_num, "records": [], "total": 0, "pages": 0,
                    "success": False, "error": str(e)}

    async def sync_pages(self, start_page: int = 1, end_page: int = 3) -> list[dict[str, Any]]:
        """同步指定范围的页数据。

        Args:
            start_page: 起始页码
            end_page: 结束页码（含）

        Returns:
            每页结果的列表
        """
        results = []

        # 打开页面获取第一页
        first_result = await self._open_page_and_wait_for_first_response()
        if not first_result:
            return [{"page_num": start_page, "records": [], "total": 0, "pages": 0,
                     "success": False, "error": "打开页面失败"}]

        if start_page == 1:
            results.append({**first_result, "error": None})
        else:
            results.append(None)  # 占位，不记录第 1 页

        current_page = 1

        # 翻页到目标范围
        for target_page in range(max(start_page, 2), end_page + 1):
            await asyncio.sleep(1)
            result = await self._click_next_page_and_capture()
            current_page += 1

            if not result:
                results.append({
                    "page_num": target_page, "records": [], "total": 0, "pages": 0,
                    "success": False, "error": f"翻页到第 {target_page} 页失败",
                })
                break

            if target_page >= start_page:
                results.append({**result, "error": None})
            else:
                results.append(None)

        # 过滤掉占位
        return [r for r in results if r is not None]

    async def get_total_pages(self) -> int | None:
        """获取总页数（需要先打开页面）"""
        result = await self._open_page_and_wait_for_first_response()
        if result:
            return result.get("pages")
        return None

    @staticmethod
    def normalize_record(record: dict) -> dict[str, Any]:
        """将 CDE 原始记录标准化。

        Args:
            record: CDE API 返回的单条记录

        Returns:
            标准化后的字典
        """
        zdyz_id = record.get("zdyzIdCODE", "")
        issue_date_str = record.get("issueDate", "").strip()

        # 解析日期
        publish_date = None
        if issue_date_str and len(issue_date_str) == 8:
            try:
                publish_date = datetime.strptime(issue_date_str, "%Y%m%d").date()
            except ValueError:
                logger.warning(f"日期解析失败: {issue_date_str}")

        # 构造原文链接
        original_url = ""
        if zdyz_id:
            original_url = CDE_DETAIL_URL_TEMPLATE.format(zdyzIdCODE=zdyz_id)

        # 分类字段（可能是逗号分隔的多个分类）
        fclass = record.get("fclass", "") or ""

        return {
            "document_id": zdyz_id,
            "title": record.get("title", ""),
            "publish_date": publish_date,
            "status_text": record.get("nowstate", ""),
            "classification": fclass,
            "original_url": original_url,
            "raw_data": record,
        }
