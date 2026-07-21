"""从 CDE 补充资料通知函 PDF 中提取药品信息和问题列表"""

import io
import logging
import re

logger = logging.getLogger(__name__)


class PDFParser:
    """CDE 通知函 PDF 解析器"""

    def __init__(self, pdf_data: bytes):
        self.pdf_data = pdf_data
        self.text = ""
        self.metadata: dict[str, str] = {}
        self.questions: list[dict] = []

    def extract_text(self) -> str:
        """提取 PDF 全文"""
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(self.pdf_data)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        self.text += page_text + "\n"
        except Exception as e:
            logger.error("pdfplumber 解析失败: %s", e)
        return self.text

    def extract_metadata(self) -> dict[str, str]:
        """提取药品元数据"""
        text = self.text or self.extract_text()

        patterns = {
            "drug_name": [
                r"药品名称[：:]\s*([^\n]+)",
                r"产品名称[：:]\s*([^\n]+)",
                r"品种名称[：:]\s*([^\n]+)",
                r"原料药[：:]\s*([^\n]+)",
            ],
            "acceptance_number": [
                r"受理号[：:]\s*([A-Z]{2,4}\d{7,10})",
                r"受理编号[：:]\s*([A-Z]{2,4}\d{7,10})",
                r"(CYHS\d{8,})",
                r"(CXHS\d{8,})",
            ],
            "registration_number": [
                r"登记号[：:]\s*(Y\d{10,12})",
                r"原辅包登记号[：:]\s*(Y\d{10,12})",
                r"(Y\d{11,12})",
            ],
            "company_name": [
                r"申请人[：:]\s*([^\n]+)",
                r"申请单位[：:]\s*([^\n]+)",
                r"企业名称[：:]\s*([^\n]+)",
                r"单位名称[：:]\s*([^\n]+)",
            ],
        }

        for field, field_patterns in patterns.items():
            for pattern in field_patterns:
                match = re.search(pattern, text)
                if match:
                    self.metadata[field] = match.group(1).strip()
                    break

        # 提取通知日期
        date_match = re.search(r"(\d{4}年\d{1,2}月\d{1,2}日)", text)
        if date_match:
            self.metadata["notice_date"] = date_match.group(1)

        return self.metadata

    def extract_questions(self) -> list[dict]:
        """提取所有问题"""
        text = self.text or self.extract_text()
        if not text:
            return []

        questions: list[dict] = []
        lines = text.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 一级标题：1、2、3...
            m1 = re.match(r"^(\d+)[、.]\s*(.+)", line)
            if m1:
                questions.append({
                    "level": 1,
                    "l1_num": m1.group(1),
                    "title": line,
                })
                continue

            # 二级标题：（1）（2）（3）...
            m2 = re.match(r"^（(\d+)）\s*(.+)", line)
            if m2:
                questions.append({
                    "level": 2,
                    "l2_num": m2.group(1),
                    "title": line,
                })
                continue

            # 三级标题：① ② ③...
            m3 = re.match(r"^([①②③④⑤⑥⑦⑧⑨⑩])\s*(.*)", line)
            if m3:
                questions.append({
                    "level": 3,
                    "l3_num": m3.group(1),
                    "title": line,
                })
                continue

        self.questions = questions
        return questions

    def parse(self) -> dict:
        """完整解析"""
        self.extract_text()
        self.extract_metadata()
        self.extract_questions()
        return {
            "metadata": self.metadata,
            "questions": self.questions,
            "question_count": len(self.questions),
        }


def parse_cde_notice(pdf_data: bytes) -> dict:
    """便捷函数：解析 CDE 通知函"""
    parser = PDFParser(pdf_data)
    return parser.parse()
