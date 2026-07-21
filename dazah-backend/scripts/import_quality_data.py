#!/usr/bin/env python3
"""
Import quality module data from CSV files.

Usage:
    python scripts/import_quality_data.py <zip_file> [--user-mapping user_mapping.json]

Example:
    python scripts/import_quality_data.py /tmp/converted.zip
    python scripts/import_quality_data.py /tmp/converted.zip --user-mapping /tmp/user_mapping.json
"""
import argparse
import asyncio
import csv
import io
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

import asyncpg


def parse_json_field(value: Optional[str]) -> Optional[dict | list]:
    """Parse JSON field, return None if empty."""
    if not value or value in ('{}', '[]', ''):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def parse_date(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO date string."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


def parse_pg_array(value: Optional[str]) -> list[str]:
    """Parse PostgreSQL array format {val1,val2}."""
    if not value or value in ('{}', ''):
        return []
    return value.strip('{}').split(',')


def load_user_mapping(path: Optional[str]) -> dict[str, str]:
    """Load user ID mapping from JSON file.
    
    Expected format: {"old_id": "new_uuid", ...}
    """
    if not path or not os.path.exists(path):
        return {}
    with open(path, 'r') as f:
        return json.load(f)


async def import_deviations(
    conn: asyncpg.Connection,
    csv_data: str,
    user_mapping: dict[str, str]
) -> int:
    """Import deviation.csv to quality.deviations."""
    reader = csv.DictReader(io.StringIO(csv_data))
    
    sql = """
        INSERT INTO quality.deviations (
            id, deviation_code, title, department, discovery_date, discovery_time,
            discovery_location, status, description, immediate_actions, reporter_id,
            handler, discoverer, level, root_cause_category, ai_analysis,
            investigation_records, review_opinions, attachments, final_code,
            returned_step, status_updated_at, needs_cross_dept_review,
            cross_dept_reviewers, affected_items, batch_number, report_content,
            report_versions, created_at, created_by, updated_at, updated_by, is_deleted
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
            $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28,
            $29, $30, $31, $32, $33
        )
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            department = EXCLUDED.department,
            status = EXCLUDED.status,
            description = EXCLUDED.description,
            updated_at = EXCLUDED.updated_at
    """
    
    count = 0
    for row in reader:
        # Map user IDs if mapping provided
        reporter_id = None
        if row.get('reporter') and row['reporter'] in user_mapping:
            reporter_id = UUID(user_mapping[row['reporter']])
        
        created_by = None
        if row.get('_created_by') and row['_created_by'] in user_mapping:
            created_by = UUID(user_mapping[row['_created_by']])
        
        updated_by = None
        if row.get('_updated_by') and row['_updated_by'] in user_mapping:
            updated_by = UUID(user_mapping[row['_updated_by']])
        
        await conn.execute(sql,
            UUID(row['id']),
            row['code'],  # deviation_code
            row.get('title'),
            row.get('department'),
            parse_date(row.get('discovery_date')),
            row.get('discovery_time'),
            row.get('discovery_location'),
            row.get('status') or 'draft',
            row.get('description'),
            None,  # immediate_actions
            reporter_id,
            row.get('handler'),
            row.get('discoverer'),
            row.get('deviation_level'),  # level
            row.get('reason_category'),  # root_cause_category
            parse_json_field(row.get('ai_analysis')),
            parse_json_field(row.get('investigation_records')),
            parse_json_field(row.get('review_opinions')),
            None,  # attachments
            row.get('final_code'),
            row.get('returned_step'),
            parse_date(row.get('status_updated_at')),
            row.get('needs_cross_dept_review', 'true').lower() == 'true',
            parse_json_field(row.get('cross_dept_reviewers')) or [],
            row.get('affected_items'),
            row.get('batch_number'),
            row.get('report_content'),
            parse_json_field(row.get('report_versions')) or [],
            parse_date(row.get('_created_at')) or datetime.now(),
            created_by,
            parse_date(row.get('_updated_at')) or datetime.now(),
            updated_by,
            False  # is_deleted
        )
        count += 1
    
    return count


async def import_capas(
    conn: asyncpg.Connection,
    csv_data: str,
    user_mapping: dict[str, str]
) -> int:
    """Import capa.csv to quality.capas."""
    reader = csv.DictReader(io.StringIO(csv_data))
    
    sql = """
        INSERT INTO quality.capas (
            id, capa_code, title, status, deviation_id, source, source_code,
            category, root_cause_category, non_conformity_description,
            root_cause_analysis, capa_content, capa_items, executors,
            expected_completion_date, qa_reviewer_id, qa_review_opinion,
            qa_review_time, q_head_approver_id, q_head_approval_opinion,
            q_head_approval_time, execution_status, execution_tracks,
            dept_head_confirmations, evaluation_result, evaluation_target,
            evaluation_deadline, evaluation_confirmer_id, evaluation_confirm_date,
            closure_date, closure_remark, final_code, report_content,
            report_versions, returned_step, status_updated_at, reporter,
            qa_confirmer, qa_confirm_date, root_cause_attachments, reason_category,
            created_at, created_by, updated_at, updated_by, is_deleted
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
            $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28,
            $29, $30, $31, $32, $33, $34, $35, $36, $37, $38, $39, $40, $41,
            $42, $43, $44, $45, $46
        )
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            status = EXCLUDED.status,
            capa_content = EXCLUDED.capa_content,
            updated_at = EXCLUDED.updated_at
    """
    
    count = 0
    for row in reader:
        # Map user IDs
        qa_reviewer_id = None
        if row.get('qa_reviewer') and row['qa_reviewer'] in user_mapping:
            qa_reviewer_id = UUID(user_mapping[row['qa_reviewer']])
        
        q_head_approver_id = None
        if row.get('q_head_approver') and row['q_head_approver'] in user_mapping:
            q_head_approver_id = UUID(user_mapping[row['q_head_approver']])
        
        evaluation_confirmer_id = None
        if row.get('evaluation_confirmer') and row['evaluation_confirmer'] in user_mapping:
            evaluation_confirmer_id = UUID(user_mapping[row['evaluation_confirmer']])
        
        created_by = None
        if row.get('_created_by') and row['_created_by'] in user_mapping:
            created_by = UUID(user_mapping[row['_created_by']])
        
        updated_by = None
        if row.get('_updated_by') and row['_updated_by'] in user_mapping:
            updated_by = UUID(user_mapping[row['_updated_by']])
        
        await conn.execute(sql,
            UUID(row['id']),
            row['code'],  # capa_code
            row.get('title'),
            row.get('status') or 'draft',
            None,  # deviation_id
            row.get('source'),
            row.get('source_code'),
            row.get('category'),
            row.get('reason_category'),  # root_cause_category
            row.get('nonconformity_description'),  # non_conformity_description
            row.get('root_cause_analysis'),
            row.get('capa_content'),
            parse_json_field(row.get('capa_items')) or [],
            None,  # executors
            parse_date(row.get('expected_completion_date')),
            qa_reviewer_id,
            row.get('qa_review_opinion'),
            parse_date(row.get('qa_review_time')),
            q_head_approver_id,
            row.get('q_head_approval_opinion'),
            parse_date(row.get('q_head_approval_time')),
            row.get('execution_status'),
            parse_json_field(row.get('execution_tracks')) or [],
            parse_json_field(row.get('dept_head_confirmations')) or [],
            row.get('evaluation_result'),
            row.get('evaluation_target'),
            parse_date(row.get('evaluation_deadline')),
            evaluation_confirmer_id,
            parse_date(row.get('evaluation_confirm_date')),
            parse_date(row.get('closure_date')),
            row.get('closure_remark'),
            row.get('final_code'),
            row.get('report_content'),
            parse_json_field(row.get('report_versions')) or [],
            row.get('returned_step'),
            parse_date(row.get('status_updated_at')),
            row.get('reporter'),
            row.get('qa_confirmer'),
            parse_date(row.get('qa_confirm_date')),
            None,  # root_cause_attachments
            row.get('reason_category'),
            parse_date(row.get('_created_at')) or datetime.now(),
            created_by,
            parse_date(row.get('_updated_at')) or datetime.now(),
            updated_by,
            False  # is_deleted
        )
        count += 1
    
    return count


async def import_department_contacts(
    conn: asyncpg.Connection,
    csv_data: str,
    user_mapping: dict[str, str]
) -> int:
    """Import department_contact.csv to quality.department_contacts."""
    reader = csv.DictReader(io.StringIO(csv_data))
    
    sql = """
        INSERT INTO quality.department_contacts (
            id, department, dept_head_id, qa_staff_ids, gmp_staff_ids,
            production_head_id, quality_head_id, additional_contacts,
            is_production_workshop, created_at, created_by, updated_at,
            updated_by, is_deleted
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
        )
        ON CONFLICT (id) DO UPDATE SET
            department = EXCLUDED.department,
            qa_staff_ids = EXCLUDED.qa_staff_ids,
            gmp_staff_ids = EXCLUDED.gmp_staff_ids,
            updated_at = EXCLUDED.updated_at
    """
    
    count = 0
    for row in reader:
        # Map user IDs
        dept_head_id = None
        if row.get('dept_head') and row['dept_head'] in user_mapping:
            dept_head_id = UUID(user_mapping[row['dept_head']])
        
        production_head_id = None
        if row.get('production_head') and row['production_head'] in user_mapping:
            production_head_id = UUID(user_mapping[row['production_head']])
        
        quality_head_id = None
        if row.get('quality_head') and row['quality_head'] in user_mapping:
            quality_head_id = UUID(user_mapping[row['quality_head']])
        
        created_by = None
        if row.get('_created_by') and row['_created_by'] in user_mapping:
            created_by = UUID(user_mapping[row['_created_by']])
        
        updated_by = None
        if row.get('_updated_by') and row['_updated_by'] in user_mapping:
            updated_by = UUID(user_mapping[row['_updated_by']])
        
        await conn.execute(sql,
            UUID(row['id']),
            row['department'],
            dept_head_id,
            parse_pg_array(row.get('qa_staff')),
            parse_pg_array(row.get('gmp_staff')),
            production_head_id,
            quality_head_id,
            parse_pg_array(row.get('additional_contacts')),
            row.get('is_production_workshop', 'false').lower() == 'true',
            parse_date(row.get('_created_at')) or datetime.now(),
            created_by,
            parse_date(row.get('_updated_at')) or datetime.now(),
            updated_by,
            False  # is_deleted
        )
        count += 1
    
    return count


async def import_weekly_confirmations(
    conn: asyncpg.Connection,
    csv_data: str,
    user_mapping: dict[str, str]
) -> int:
    """Import department_weekly_confirmation.csv to quality.department_weekly_confirmations."""
    reader = csv.DictReader(io.StringIO(csv_data))
    
    sql = """
        INSERT INTO quality.department_weekly_confirmations (
            id, department, week_key, production_status, deviation_status,
            confirmed_by_id, confirmed_at, created_at, created_by, updated_at,
            updated_by, is_deleted
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
        )
        ON CONFLICT (id) DO UPDATE SET
            production_status = EXCLUDED.production_status,
            deviation_status = EXCLUDED.deviation_status,
            confirmed_at = EXCLUDED.confirmed_at,
            updated_at = EXCLUDED.updated_at
    """
    
    count = 0
    for row in reader:
        # Map user IDs
        confirmed_by_id = None
        if row.get('confirmed_by') and row['confirmed_by'] in user_mapping:
            confirmed_by_id = UUID(user_mapping[row['confirmed_by']])
        
        created_by = None
        if row.get('_created_by') and row['_created_by'] in user_mapping:
            created_by = UUID(user_mapping[row['_created_by']])
        
        updated_by = None
        if row.get('_updated_by') and row['_updated_by'] in user_mapping:
            updated_by = UUID(user_mapping[row['_updated_by']])
        
        await conn.execute(sql,
            UUID(row['id']),
            row['department'],
            row['week_key'],
            row.get('production_status'),
            row.get('deviation_status') or 'unsubmitted',
            confirmed_by_id,
            parse_date(row.get('confirmed_at')),
            parse_date(row.get('_created_at')) or datetime.now(),
            created_by,
            parse_date(row.get('_updated_at')) or datetime.now(),
            updated_by,
            False  # is_deleted
        )
        count += 1
    
    return count


async def main():
    parser = argparse.ArgumentParser(description='Import quality data from CSV zip')
    parser.add_argument('zip_file', help='Path to zip file containing CSVs')
    parser.add_argument('--user-mapping', help='Path to user ID mapping JSON file')
    parser.add_argument('--db-url', default='postgresql://erp_user:LivzonSyntpharm@postgres:5432/erp',
                        help='Database URL')
    args = parser.parse_args()
    
    # Load user mapping
    user_mapping = load_user_mapping(args.user_mapping)
    if user_mapping:
        print(f"Loaded {len(user_mapping)} user ID mappings")
    
    # Extract CSVs from zip
    print(f"Reading {args.zip_file}...")
    with zipfile.ZipFile(args.zip_file, 'r') as z:
        deviation_csv = z.read('deviation.csv').decode('utf-8')
        capa_csv = z.read('capa.csv').decode('utf-8')
        dept_csv = z.read('department_contact.csv').decode('utf-8')
        weekly_csv = z.read('department_weekly_confirmation.csv').decode('utf-8')
    
    # Connect to database
    print("Connecting to database...")
    conn = await asyncpg.connect(args.db_url)
    
    try:
        async with conn.transaction():
            print("Importing deviations...")
            dev_count = await import_deviations(conn, deviation_csv, user_mapping)
            print(f"  → {dev_count} rows")
            
            print("Importing capas...")
            capa_count = await import_capas(conn, capa_csv, user_mapping)
            print(f"  → {capa_count} rows")
            
            print("Importing department contacts...")
            dept_count = await import_department_contacts(conn, dept_csv, user_mapping)
            print(f"  → {dept_count} rows")
            
            print("Importing weekly confirmations...")
            weekly_count = await import_weekly_confirmations(conn, weekly_csv, user_mapping)
            print(f"  → {weekly_count} rows")
        
        print(f"\n✓ Migration completed successfully!")
        print(f"  Total: {dev_count + capa_count + dept_count + weekly_count} rows imported")
        
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        raise
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
