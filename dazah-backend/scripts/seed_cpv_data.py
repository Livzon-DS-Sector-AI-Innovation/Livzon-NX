#!/usr/bin/env python3
"""
CPV 种子数据导入脚本
从飞书导出的 JSON 文件导入数据到 PostgreSQL 数据库
"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

import asyncpg


DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/dazah"

PRODUCT_NAME = "头孢曲松钠原料药"
PRODUCT_SPEC = "1.0g"
PROCESS_VERSION = "V1.0"

CPP_PARAMETERS = [
    {"name": "批量(kg)", "code": "batch_kg_221_260kg", "unit": "kg", "sort_order": 1},
    {"name": "收率(%)", "code": "yield_percent", "unit": "%", "lower_limit": 85, "upper_limit": 100, "sort_order": 2},
    {"name": "溶解温度(°C)", "code": "dissolution_temperature", "unit": "°C", "lower_limit": 15, "upper_limit": 20, "sort_order": 3},
    {"name": "结晶控温最大(°C)", "code": "crystal_temperature_max", "unit": "°C", "lower_limit": 15, "upper_limit": 25, "sort_order": 4},
    {"name": "结晶控温最小(°C)", "code": "cryo_temp_min", "unit": "°C", "lower_limit": 15, "upper_limit": 25, "sort_order": 5},
    {"name": "结晶完毕降温至(°C)", "code": "cryo_cool_down", "unit": "°C", "lower_limit": 2, "upper_limit": 10, "sort_order": 6},
    {"name": "双锥夹套热水温度最大(°C)", "code": "cone_hot_water_max", "unit": "°C", "lower_limit": 53, "upper_limit": 55, "sort_order": 7},
    {"name": "双锥夹套热水温度最小(°C)", "code": "cone_hot_water_min", "unit": "°C", "lower_limit": 53, "upper_limit": 55, "sort_order": 8},
]

CQA_PARAMETERS = [
    {"name": "溶液颜色", "code": "solution_color", "unit": "", "upper_limit": 6, "sort_order": 1},
    {"name": "pH值", "code": "ph_value", "unit": "", "lower_limit": 6, "upper_limit": 8, "sort_order": 2},
    {"name": "未知单杂(%)", "code": "other_single_unknown_impurity_pct", "unit": "%", "upper_limit": 0.4, "sort_order": 3},
    {"name": "总杂(%)", "code": "total_impurity_pct", "unit": "%", "upper_limit": 0.8, "sort_order": 4},
    {"name": "头孢曲松聚合物(%)", "code": "ceftriaxone_sodium_polymer_pct", "unit": "%", "upper_limit": 0.4, "sort_order": 5},
    {"name": "含量(%)", "code": "content_percent", "unit": "%", "lower_limit": 90, "sort_order": 6},
    {"name": "残留甲醇(%)", "code": "residual_methanol_percent", "unit": "%", "upper_limit": 0.3, "sort_order": 7},
    {"name": "残留乙醇(%)", "code": "residual_ethanol_percent", "unit": "%", "upper_limit": 0.5, "sort_order": 8},
    {"name": "残留乙腈", "code": "residual_acetonitrile", "unit": "%", "upper_limit": 0.041, "sort_order": 9},
    {"name": "残留丙酮", "code": "residue_acetone", "unit": "%", "upper_limit": 0.4, "sort_order": 10},
    {"name": "残留二氯甲烷", "code": "residue_dichloromethane", "unit": "%", "upper_limit": 0.06, "sort_order": 11},
    {"name": "残留乙酸乙酯", "code": "residue_ethyl_acetate", "unit": "%", "upper_limit": 0.4, "sort_order": 12},
    {"name": "水分(%)", "code": "moisture", "unit": "%", "lower_limit": 8.5, "upper_limit": 10.5, "sort_order": 13},
]

# CQA 字段映射（JSON 中的实际字段名 -> 参数 code）
CQA_FIELD_MAP = {
    "solution_color": "solution_color",
    "ph_value": "ph_value",
    "other_single_unknown_impurity_pct": "other_single_unknown_impurity_pct",
    "total_impurity_pct": "total_impurity_pct",
    "ceftriaxone_sodium_polymer_pct": "ceftriaxone_sodium_polymer_pct",
    "含量_%": "content_percent",
    "残留甲醇_%": "residual_methanol_percent",
    "残留乙醇_%": "residual_ethanol_percent",
    "residual_acetonitrile": "residual_acetonitrile",
    "residue_acetone": "residue_acetone",
    "residue_dichloromethane": "residue_dichloromethane",
    "residue_ethyl_acetate": "residue_ethyl_acetate",
    "moisture": "moisture",
}


def parse_value(value):
    """解析参数值，处理 '未检出' 等特殊值"""
    if value is None:
        return None
    if value == "未检出":
        return 0.0
    if value == "符合规定":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def check_abnormal(value, param_def):
    """检查值是否超出规格限"""
    if value is None or param_def is None:
        return False
    ll = param_def.get("lower_limit")
    ul = param_def.get("upper_limit")
    if ll is not None and value < ll:
        return True
    if ul is not None and value > ul:
        return True
    return False


async def main():
    print("开始导入 CPV 数据...")

    conn = await asyncpg.connect(DATABASE_URL)
    print(f"✓ 数据库连接成功: {DATABASE_URL}")

    try:
        schema_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = $1)",
            "quality"
        )
        if not schema_exists:
            print("✗ quality schema 不存在，请先运行 alembic upgrade head")
            return

        # 1. 创建产品
        product_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO quality.cpv_products
                (id, name, specification, process_version, status, description,
                 created_at, updated_at, is_deleted)
            VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW(), false)
            ON CONFLICT (id) DO NOTHING
            """,
            product_id, PRODUCT_NAME, PRODUCT_SPEC, PROCESS_VERSION,
            "active", "头孢曲松钠原料药持续工艺验证产品"
        )
        print(f"✓ 产品创建成功: {PRODUCT_NAME} (ID: {product_id})")

        # 2. 创建 CPP 参数
        cpp_param_ids = {}
        for param in CPP_PARAMETERS:
            param_id = uuid.uuid4()
            cpp_param_ids[param["code"]] = param_id
            await conn.execute(
                """
                INSERT INTO quality.cpv_parameters
                    (id, product_id, parameter_type, name, code, unit,
                     lower_limit, upper_limit, is_enabled, sort_order,
                     created_at, updated_at, is_deleted)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, true, $9, NOW(), NOW(), false)
                ON CONFLICT (id) DO NOTHING
                """,
                param_id, product_id, "CPP", param["name"], param["code"],
                param.get("unit"), param.get("lower_limit"),
                param.get("upper_limit"), param["sort_order"]
            )
        print(f"✓ CPP 参数创建成功: {len(CPP_PARAMETERS)} 个")

        # 3. 创建 CQA 参数
        cqa_param_ids = {}
        for param in CQA_PARAMETERS:
            param_id = uuid.uuid4()
            cqa_param_ids[param["code"]] = param_id
            await conn.execute(
                """
                INSERT INTO quality.cpv_parameters
                    (id, product_id, parameter_type, name, code, unit,
                     lower_limit, upper_limit, is_enabled, sort_order,
                     created_at, updated_at, is_deleted)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, true, $9, NOW(), NOW(), false)
                ON CONFLICT (id) DO NOTHING
                """,
                param_id, product_id, "CQA", param["name"], param["code"],
                param.get("unit"), param.get("lower_limit"),
                param.get("upper_limit"), param["sort_order"]
            )
        print(f"✓ CQA 参数创建成功: {len(CQA_PARAMETERS)} 个")

        # 4. 导入 CPP 批次数据
        cpp_json_path = Path("/tmp/CPV/q2_2025_cpp.json")
        if cpp_json_path.exists():
            with open(cpp_json_path, encoding="utf-8") as f:
                cpp_data = json.load(f)

            batch_count = 0
            value_count = 0
            for record in cpp_data["data"]:
                batch_id = uuid.uuid4()
                # CPP JSON 使用 product_batch 字段
                batch_no = record.get("product_batch", record.get("product_batch_no", "UNKNOWN"))
                prod_date_str = record.get("production_date", "2025-01-01T00:00:00Z")
                prod_date = datetime.fromisoformat(
                    prod_date_str.replace("Z", "+00:00")
                ).date()

                await conn.execute(
                    """
                    INSERT INTO quality.cpv_batches
                        (id, product_id, batch_no, production_date,
                         data_type, source, created_at, updated_at, is_deleted)
                    VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW(), false)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    batch_id, product_id, batch_no, prod_date, "CPP", "feishu"
                )
                batch_count += 1

                for param_code, param_id in cpp_param_ids.items():
                    if param_code in record and record[param_code] is not None:
                        value = parse_value(record[param_code])
                        if value is None:
                            continue
                        param_def = next(
                            (p for p in CPP_PARAMETERS if p["code"] == param_code),
                            None,
                        )
                        is_abnormal = check_abnormal(value, param_def)

                        await conn.execute(
                            """
                            INSERT INTO quality.cpv_values
                                (id, batch_id, parameter_id, actual_value,
                                 is_abnormal, created_at, updated_at, is_deleted)
                            VALUES ($1, $2, $3, $4, $5, NOW(), NOW(), false)
                            ON CONFLICT (id) DO NOTHING
                            """,
                            uuid.uuid4(), batch_id, param_id,
                            str(value), is_abnormal
                        )
                        value_count += 1

            print(f"✓ CPP 批次导入成功: {batch_count} 批次, {value_count} 个参数值")
        else:
            print(f"✗ CPP 数据文件不存在: {cpp_json_path}")

        # 5. 导入 CQA 批次数据
        cqa_json_path = Path("/tmp/CPV/q2_2025_cqa.json")
        if cqa_json_path.exists():
            with open(cqa_json_path, encoding="utf-8") as f:
                cqa_data = json.load(f)

            batch_count = 0
            value_count = 0
            for record in cqa_data["data"]:
                batch_id = uuid.uuid4()
                # CQA JSON 使用 product_batch_no 字段
                batch_no = record.get("product_batch_no", record.get("product_batch", "UNKNOWN"))
                prod_date_str = record.get("production_date", "2025-01-01T00:00:00Z")
                prod_date = datetime.fromisoformat(
                    prod_date_str.replace("Z", "+00:00")
                ).date()

                await conn.execute(
                    """
                    INSERT INTO quality.cpv_batches
                        (id, product_id, batch_no, production_date,
                         data_type, source, created_at, updated_at, is_deleted)
                    VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW(), false)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    batch_id, product_id, batch_no, prod_date, "CQA", "feishu"
                )
                batch_count += 1

                for json_field, param_code in CQA_FIELD_MAP.items():
                    if json_field not in record:
                        continue
                    raw_value = record[json_field]
                    value = parse_value(raw_value)
                    if value is None:
                        continue

                    param_id = cqa_param_ids.get(param_code)
                    if param_id is None:
                        continue

                    param_def = next(
                        (p for p in CQA_PARAMETERS if p["code"] == param_code),
                        None,
                    )
                    is_abnormal = check_abnormal(value, param_def)

                    await conn.execute(
                        """
                        INSERT INTO quality.cpv_values
                            (id, batch_id, parameter_id, actual_value,
                             is_abnormal, created_at, updated_at, is_deleted)
                        VALUES ($1, $2, $3, $4, $5, NOW(), NOW(), false)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        uuid.uuid4(), batch_id, param_id,
                        str(value), is_abnormal
                    )
                    value_count += 1

            print(f"✓ CQA 批次导入成功: {batch_count} 批次, {value_count} 个参数值")
        else:
            print(f"✗ CQA 数据文件不存在: {cqa_json_path}")

        print("\n✓ 数据导入完成！")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
