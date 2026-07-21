"""从 COA（检验报告/分析证书）PDF 中提取对照物质信息"""

import io
import logging
import re

logger = logging.getLogger(__name__)


class COAParser:
    """COA PDF 解析器"""

    def __init__(self, pdf_data: bytes):
        self.pdf_data = pdf_data
        self.text = ""
        self.metadata: dict[str, str] = {}

    def extract_text(self) -> str:
        """提取 PDF 全文"""
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(self.pdf_data)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        self.text += page_text + "\n"
        except ImportError:
            logger.error("pdfplumber 未安装")
        except Exception as e:
            logger.error("pdfplumber 解析失败: %s", e)
        return self.text

    def extract_metadata(self) -> dict[str, str]:
        """从 COA 中提取对照物质相关信息"""
        text = self.text or self.extract_text()
        if not text:
            return {}

        # 药品名称 - 匹配 "Product Name: xxx"
        patterns_drug_name = [
            r"Product Name[:\s]+([^\n]+)",
            r"药品名称[：:\s]+([^\n]+)",
            r"产品名称[：:\s]+([^\n]+)",
        ]
        for pattern in patterns_drug_name:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["drug_name"] = match.group(1).strip()[:100]
                break

        # 对照物质名称 - 通常和药品名称相同，或者在 Chemical Name 中
        patterns_substance = [
            r"Chemical Name[:\s]+([^\n]+)",
            r"对照物质[：:\s]+([^\n]+)",
            r"对照品[：:\s]+([^\n]+)",
        ]
        for pattern in patterns_substance:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["reference_substance_name"] = match.group(1).strip()[:200]
                break

        # 批号 - 匹配 "Lot #:" 或 "Lot No:" 或 "Batch No:"
        patterns_batch = [
            r"Lot\s*#[:\s]+([A-Z0-9\-]+)",
            r"Lot\s*No\.?[:\s]+([A-Z0-9\-]+)",
            r"Batch\s*No\.?[:\s]+([A-Z0-9\-]+)",
            r"批号[：:\s]+([A-Z0-9\-]+)",
        ]
        for pattern in patterns_batch:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["batch_number"] = match.group(1).strip()
                break

        # 生产厂家 - 从文本开头提取公司名
        patterns_manufacturer = [
            r"Manufacturer[:\s]+([^\n]+)",
            r"Supplier[:\s]+([^\n]+)",
            r"生产厂家[：:\s]+([^\n]+)",
            r"生产商[：:\s]+([^\n]+)",
        ]
        for pattern in patterns_manufacturer:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["manufacturer"] = match.group(1).strip()[:200]
                break
        
        # 如果没有找到，尝试从文本开头提取（通常是公司名）
        if "manufacturer" not in self.metadata:
            lines = text.split('\n')
            for line in lines[:5]:  # 只看前 5 行
                line = line.strip()
                # 匹配包含 Co., Ltd, Corporation, Inc 等的行
                if re.search(r'(Co\.?\s*,?\s*LTD|Corporation|Inc\.?|Company|公司)', line, re.IGNORECASE):
                    self.metadata["manufacturer"] = line[:200]
                    break

        # 英文名 - 通常和 Product Name 相同
        patterns_english = [
            r"English Name[:\s]+([^\n]+)",
            r"英文名[：:\s]+([^\n]+)",
        ]
        for pattern in patterns_english:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["english_name"] = match.group(1).strip()[:200]
                break
        
        # 如果没有英文名，使用 Product Name
        if "english_name" not in self.metadata and "drug_name" in self.metadata:
            self.metadata["english_name"] = self.metadata["drug_name"]

        # CAS号 - 匹配 "CAS Number:" 或 "CAS No:"
        patterns_cas = [
            r"CAS\s*Number[:\s]+(\d{2,7}-\d{2}-\d)",
            r"CAS\s*No\.?[:\s]+(\d{2,7}-\d{2}-\d)",
            r"CAS[：:\s]+(\d{2,7}-\d{2}-\d)",
            r"(\d{2,7}-\d{2}-\d)",  # 直接匹配 CAS 格式
        ]
        for pattern in patterns_cas:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["cas_number"] = match.group(1).strip()
                break

        # 分子式 - 匹配 Molecular Formula
        patterns_formula = [
            r"Molecular\s*Formula[:\s]+([A-Z][a-zA-Z0-9()]+)",
            r"分子式[：:\s]+([A-Z][a-zA-Z0-9()]+)",
            r"Formula[:\s]+([A-Z][a-zA-Z0-9()]+)",
        ]
        for pattern in patterns_formula:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                formula = match.group(1).strip()
                if re.match(r'^[A-Z][a-zA-Z0-9()]+$', formula) and len(formula) > 3:
                    self.metadata["molecular_formula"] = formula
                    break

        # 分子量 - 匹配 "Average Molecular Weight" 或 "Molecular Weight"
        patterns_weight = [
            r"Average\s+Molecular\s+Weight\s+(\d+)",
            r"Molecular\s+Weight[:\s]+(\d+\.?\d*)",
            r"分子量[：:\s]+(\d+\.?\d*)",
            r"MW[:\s]+(\d+\.?\d*)",
        ]
        for pattern in patterns_weight:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["molecular_weight"] = match.group(1).strip()
                break

        # 含量 - 匹配 "Analysis" 或 "Assay" 或 "Purity"
        patterns_content = [
            r"Analysis[:\s]+(\d+)",
            r"Assay[:\s]+(\d+\.?\d*)\s*%?",
            r"Purity[:\s]+(\d+\.?\d*)\s*%?",
            r"含量[：:\s]+(\d+\.?\d*)\s*%?",
            r"纯度[：:\s]+(\d+\.?\d*)\s*%?",
        ]
        for pattern in patterns_content:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["content"] = match.group(1).strip()
                break

        # 水分/干燥失重 - 匹配 "Loss on drying"
        patterns_moisture = [
            r"Loss\s+on\s+drying\s+\d+-\d+[（(]%[）)]?\s+(\d+\.?\d*)\s*%?",
            r"Loss\s+on\s+drying[:\s]+(\d+\.?\d*)\s*%?",
            r"Moisture[:\s]+(\d+\.?\d*)\s*%?",
            r"水分[：:\s]+(\d+\.?\d*)\s*%?",
            r"干燥失重[：:\s]+(\d+\.?\d*)\s*%?",
        ]
        for pattern in patterns_moisture:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["moisture"] = match.group(1).strip()
                break

        # RSD - 匹配 "RSD" 或 "Relative Standard Deviation"
        patterns_rsd = [
            r"RSD[:\s]+(\d+\.?\d*)\s*%?",
            r"R\.S\.D\.[:\s]+(\d+\.?\d*)\s*%?",
            r"Relative\s+Standard\s+Deviation[:\s]+(\d+\.?\d*)\s*%?",
        ]
        for pattern in patterns_rsd:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["rsd"] = match.group(1).strip()
                break

        # 有效期 - 优先使用 "Date of Next Testing" 或 "Retest Date"
        patterns_expiry = [
            r"Date\s+of\s+Next\s+Testing[:\s]+(\d{4}-\d{2}-\d{2})",
            r"Retest\s+Date[:\s]+(\d{4}-\d{2}-\d{2})",
            r"Expiration\s+Date[:\s]+(\d{4}-\d{2}-\d{2})",
            r"Expiry\s+Date[:\s]+(\d{4}-\d{2}-\d{2})",
            r"有效期[：:\s]+(\d{4}-\d{2}-\d{2})",
            r"复验期[：:\s]+(\d{4}-\d{2}-\d{2})",
            r"Use\s+by[:\s]+(\d{4}-\d{2}-\d{2})",
        ]
        for pattern in patterns_expiry:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["expiration_date"] = match.group(1).strip()
                break
        
        # 如果没有找到，尝试从 "Date of Testing" 推算（加 4 年）
        if "expiration_date" not in self.metadata:
            match = re.search(r"Date\s+of\s+Testing[:\s]+(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
            if match:
                from datetime import datetime, timedelta
                try:
                    test_date = datetime.strptime(match.group(1), "%Y-%m-%d")
                    expiry_date = test_date + timedelta(days=4*365)  # 假设 4 年有效期
                    self.metadata["expiration_date"] = expiry_date.strftime("%Y-%m-%d")
                except:
                    pass

        # 贮存条件 - 匹配 "Storage Temperature" 或 "Storage Condition"
        patterns_storage = [
            r"Storage\s+Temperature[:\s]+([^\n]+)",
            r"Storage\s+Condition[:\s]+([^\n]+)",
            r"Storage[:\s]+([^\n]+)",
            r"贮存条件[：:\s]+([^\n]+)",
            r"储存条件[：:\s]+([^\n]+)",
        ]
        for pattern in patterns_storage:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                storage_text = match.group(1).strip()
                # 智能识别贮存条件
                storage_lower = storage_text.lower()
                if any(kw in storage_lower for kw in ["-20", "- 20", "20°c", "frozen", "冷冻"]):
                    self.metadata["storage_condition"] = "冷冻"
                elif any(kw in storage_lower for kw in ["2-8", "2~8", "2℃-8℃", "cold", "冷藏"]):
                    self.metadata["storage_condition"] = "冷藏"
                elif any(kw in storage_lower for kw in ["room", "常温", "室温", "25"]):
                    self.metadata["storage_condition"] = "常温"
                elif any(kw in storage_lower for kw in ["cool", "阴凉", "15"]):
                    self.metadata["storage_condition"] = "阴凉"
                else:
                    # 保留原始文本，但截取合理长度
                    self.metadata["storage_condition"] = storage_text[:100]
                break

        return self.metadata

    def parse(self) -> dict:
        """完整解析 COA"""
        self.extract_text()
        self.extract_metadata()
        return {
            "metadata": self.metadata,
            "raw_text": self.text[:2000],  # 返回前 2000 字符用于调试
        }


def parse_coa(pdf_data: bytes) -> dict:
    """便捷函数：解析 COA PDF"""
    parser = COAParser(pdf_data)
    return parser.parse()
