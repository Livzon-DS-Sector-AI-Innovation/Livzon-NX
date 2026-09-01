from __future__ import annotations

from datetime import date

from app.modules.regulatory_tracker.crawler.adapters.domestic import (
    CfdiCrawlerAdapter,
    IvdcCrawlerAdapter,
    MoaCrawlerAdapter,
    NmpaCrawlerAdapter,
    _parse_detail_page,
)
from app.modules.regulatory_tracker.crawler.types import CrawledRegulationRecord


def test_nmpa_parse_list_page_extracts_drug_documents() -> None:
    adapter = NmpaCrawlerAdapter(max_pages=1)
    page_html = """
    <html>
      <body>
        <ul>
          <li>
            <a href="./20260325162502165.html">
              国家药监局关于印发药品现代物流规范化建设指导意见的通知
            </a>
            (2026-03-25)
          </li>
          <li>
            <a href="https://www.cde.org.cn/main/news/viewInfoCommon/b93aba16ec47467317057dca4aac8437">
              2025年度药品审评报告
            </a>
            (2026-05-13)
          </li>
        </ul>
      </body>
    </html>
    """

    records = adapter._parse_list_page(page_html, adapter.list_url)

    assert records == [
        CrawledRegulationRecord(
            source_site="nmpa",
            document_id="nmpa:20260325162502165",
            title="国家药监局关于印发药品现代物流规范化建设指导意见的通知",
            original_url=(
                "https://www.nmpa.gov.cn/directory/web/nmpa/xxgk/fgwj/gzwj/gzwjyp/"
                "20260325162502165.html"
            ),
            publish_date=date(2026, 3, 25),
            effective_date=None,
            version=None,
            summary=None,
            raw_data={
                "list_page_url": adapter.list_url,
                "list_text": "国家药监局关于印发药品现代物流规范化建设指导意见的通知",
                "detail_url": (
                    "https://www.nmpa.gov.cn/directory/web/nmpa/xxgk/fgwj/gzwj/gzwjyp/"
                    "20260325162502165.html"
                ),
            },
        )
    ]


def test_cfdi_parse_list_page_keeps_only_cfdi_origin_links() -> None:
    adapter = CfdiCrawlerAdapter()
    page_html = """
    <html>
      <body>
        <a href="https://cfdi.org.cn/cfdi/resource/news/16700.html">
          关于发布《制药用水检查指南》的通告2026-03-31
        </a>
        <a href="https://www.cde.org.cn/main/news/viewInfoCommon/abc123">
          国家药监局药审中心关于发布指导原则的通告2026-03-10
        </a>
      </body>
    </html>
    """

    records = adapter._parse_list_page(page_html, adapter.list_url)

    assert records == [
        CrawledRegulationRecord(
            source_site="cfdi",
            document_id="cfdi:16700",
            title="关于发布《制药用水检查指南》的通告",
            original_url="https://cfdi.org.cn/cfdi/resource/news/16700.html",
            publish_date=date(2026, 3, 31),
            effective_date=None,
            version=None,
            summary=None,
            raw_data={
                "list_page_url": adapter.list_url,
                "list_text": "关于发布《制药用水检查指南》的通告2026-03-31",
                "detail_url": "https://cfdi.org.cn/cfdi/resource/news/16700.html",
            },
        )
    ]


def test_moa_parse_list_page_extracts_announcement_records() -> None:
    adapter = MoaCrawlerAdapter(max_pages=1)
    page_html = """
    <html>
      <body>
        <a href="./202604/t20260428_6483711.htm">
          中华人民共和国农业农村部公告 第1015号2026-04-28
        </a>
        <a href="../">畜牧兽医局</a>
      </body>
    </html>
    """

    records = adapter._parse_list_page(page_html, adapter.list_url)

    assert records == [
        CrawledRegulationRecord(
            source_site="moa",
            document_id="moa:6483711",
            title="中华人民共和国农业农村部公告 第1015号",
            original_url="https://xmsyj.moa.gov.cn/zwfw/202604/t20260428_6483711.htm",
            publish_date=date(2026, 4, 28),
            effective_date=None,
            version=None,
            summary=None,
            raw_data={
                "list_page_url": adapter.list_url,
                "list_text": "中华人民共和国农业农村部公告 第1015号2026-04-28",
                "detail_url": "https://xmsyj.moa.gov.cn/zwfw/202604/t20260428_6483711.htm",
            },
        )
    ]


def test_ivdc_parse_list_page_extracts_guideline_rows() -> None:
    adapter = IvdcCrawlerAdapter(max_pages=1)
    page_html = """
    <html>
      <body>
        <table>
          <tr>
            <th>序号</th>
            <th>指导原则名称</th>
            <th>版本</th>
            <th>发布日期</th>
          </tr>
          <tr>
            <td>1</td>
            <td>
              <a href="./202408/P020241223588326742521.docx">
                水产养殖用消毒剂药效试验技术指导原则
              </a>
              版本：颁布
              2024-08-22
            </td>
            <td>颁布</td>
            <td>2024-08-22</td>
          </tr>
        </table>
      </body>
    </html>
    """

    records = adapter._parse_list_page(page_html, adapter.list_url)

    assert records == [
        CrawledRegulationRecord(
            source_site="ivdc",
            document_id="ivdc:P020241223588326742521",
            title="水产养殖用消毒剂药效试验技术指导原则",
            original_url=(
                "http://www.ivdc.org.cn/pszx/ywgz/zdyz/sjk/hxy/202408/"
                "P020241223588326742521.docx"
            ),
            publish_date=date(2024, 8, 22),
            effective_date=None,
            version="颁布",
            summary=None,
            raw_data={
                "list_page_url": adapter.list_url,
                "row_values": [
                    "1",
                    "水产养殖用消毒剂药效试验技术指导原则 版本：颁布 2024-08-22",
                    "颁布",
                    "2024-08-22",
                ],
                "detail_url": (
                    "http://www.ivdc.org.cn/pszx/ywgz/zdyz/sjk/hxy/202408/"
                    "P020241223588326742521.docx"
                ),
            },
        )
    ]


def test_parse_detail_page_extracts_detail_content_and_paragraphs() -> None:
    detail_html = """
    <html>
      <body>
        <h1>关于发布《化学原料药变更研究技术指导原则》的通告</h1>
        <div>发布时间：2026-07-14</div>
        <p>为加强化学原料药上市后变更管理，现发布本指导原则。</p>
        <p>本文件适用于已上市化学原料药生产工艺、质量标准和包装材料变更研究。</p>
      </body>
    </html>
    """

    result = _parse_detail_page(
        detail_html,
        publish_date_label="发布时间",
        fallback_title="占位标题",
    )

    assert result["title"] == "关于发布《化学原料药变更研究技术指导原则》的通告"
    assert result["publish_date"] == date(2026, 7, 14)
    assert result["raw_data"]["detail_excerpt"] == (
        "为加强化学原料药上市后变更管理，现发布本指导原则。 "
        "本文件适用于已上市化学原料药生产工艺、质量标准和包装材料变更研究。"
    )
    assert result["raw_data"]["detail_content"] == (
        "为加强化学原料药上市后变更管理，现发布本指导原则。 "
        "本文件适用于已上市化学原料药生产工艺、质量标准和包装材料变更研究。"
    )
    assert result["raw_data"]["detail_paragraphs"] == [
        "为加强化学原料药上市后变更管理，现发布本指导原则。",
        "本文件适用于已上市化学原料药生产工艺、质量标准和包装材料变更研究。",
    ]
