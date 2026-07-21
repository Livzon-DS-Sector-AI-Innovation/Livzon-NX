"""
导出生产管理标签复核数据为 SQL 文件
用法: cd dazah-backend && source venv/bin/activate && unset DEBUG && python3 scripts/export_label_verification_sql.py
输出: /mnt/c/Users/chenlinxin/Desktop/codex资料/导出数据/标签复核数据_<时间戳>.sql
"""
import asyncio
from sqlalchemy import text
from app.core.database import engine
from datetime import date, datetime
import os

OUTPUT_DIR = "/mnt/c/Users/chenlinxin/Desktop/codex资料/导出数据"


async def export_label_verification_sql():
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT * FROM production.label_verifications WHERE is_deleted = false ORDER BY verification_date"
        ))
        rows = result.fetchall()
        columns = result.keys()

        print(f"共 {len(rows)} 条数据")

        lines = []
        lines.append("-- =============================================")
        lines.append("-- 生产管理 - 标签复核数据导出")
        lines.append(f"-- 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"-- 共 {len(rows)} 条记录")
        lines.append("-- =============================================")
        lines.append("")
        lines.append("SET client_encoding = 'UTF8';")
        lines.append("SET standard_conforming_strings = on;")
        lines.append("")

        def fmt(v):
            if v is None:
                return "NULL"
            if isinstance(v, bool):
                return "TRUE" if v else "FALSE"
            if isinstance(v, (int, float)):
                return str(v)
            if isinstance(v, date):
                return f"'{v.isoformat()}'"
            if isinstance(v, datetime):
                return f"'{v.isoformat()}'"
            if hasattr(v, 'hex'):
                return f"'{v}'"
            s = str(v).replace("'", "''")
            return f"'{s}'"

        for row in rows:
            data = dict(zip(columns, row))
            cols = ", ".join(columns)
            vals = ", ".join(fmt(data[c]) for c in columns)
            lines.append(f"INSERT INTO production.label_verifications ({cols}) VALUES ({vals});")

        lines.append("")
        lines.append(f"-- 导出完成，共 {len(rows)} 条 INSERT 语句")

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{OUTPUT_DIR}/标签复核数据_{timestamp}.sql"

        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"导出成功: {filename}")


if __name__ == "__main__":
    asyncio.run(export_label_verification_sql())
