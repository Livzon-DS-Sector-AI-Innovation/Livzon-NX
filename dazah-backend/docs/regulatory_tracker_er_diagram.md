# Regulatory Tracker ER Diagram

## Entity Relationship Diagram

```mermaid
erDiagram
    DATA_SOURCES ||--o{ DATA_CHANNELS : "has"
    DATA_SOURCES ||--o{ REGULATORY_DOCUMENTS : "contains"
    DATA_SOURCES ||--o{ SYNC_JOBS : "triggers"
    
    DATA_CHANNELS ||--o{ REGULATORY_DOCUMENTS : "categorizes"
    DATA_CHANNELS ||--o{ SYNC_JOBS : "executes"

    DATA_SOURCES {
        uuid id PK
        string code UK "CDE, NMPA, FDA"
        string name "数据源名称"
        string base_url "基础URL"
        boolean enabled "是否启用"
        datetime created_at
        datetime updated_at
        uuid created_by FK
        uuid updated_by FK
        boolean is_deleted
    }

    DATA_CHANNELS {
        uuid id PK
        uuid source_id FK "所属数据源ID"
        string code UK "栏目编码"
        string name "栏目名称"
        string list_url "列表页URL"
        string adapter_name "适配器名称"
        boolean enabled "是否启用"
        datetime created_at
        datetime updated_at
        uuid created_by FK
        uuid updated_by FK
        boolean is_deleted
    }

    REGULATORY_DOCUMENTS {
        uuid id PK
        uuid source_id FK "数据源ID"
        uuid channel_id FK "栏目ID"
        string document_id "文档唯一标识"
        string title "标题"
        date publish_date "发布日期"
        string status_text "状态文本"
        string classification "分类"
        string original_url "原文链接"
        boolean is_new "是否新发现"
        boolean is_read "是否已读"
        datetime first_found_at "首次发现时间"
        datetime last_checked_at "最后检查时间"
        jsonb raw_data "原始JSON数据"
        string unique_key "备用去重键"
        datetime created_at
        datetime updated_at
        uuid created_by FK
        uuid updated_by FK
        boolean is_deleted
    }

    SYNC_JOBS {
        uuid id PK
        uuid source_id FK "数据源ID"
        uuid channel_id FK "栏目ID"
        string job_type "任务类型"
        datetime started_at "开始时间"
        datetime finished_at "结束时间"
        string status "状态"
        integer checked_count "检查数量"
        integer new_count "新增数量"
        integer updated_count "更新数量"
        text error_message "错误信息"
        datetime created_at
        datetime updated_at
        uuid created_by FK
        uuid updated_by FK
        boolean is_deleted
    }
```

## Constraints

### Unique Constraints

- `data_sources.code`: 数据源编码唯一
- `data_channels(source_id, code)`: 同一数据源下栏目编码唯一
- `regulatory_documents(source_id, channel_id, document_id)`: 同一栏目下文档ID唯一

### Foreign Keys

- `data_channels.source_id` → `data_sources.id` (CASCADE DELETE)
- `regulatory_documents.source_id` → `data_sources.id` (CASCADE DELETE)
- `regulatory_documents.channel_id` → `data_channels.id` (CASCADE DELETE)
- `sync_jobs.source_id` → `data_sources.id` (CASCADE DELETE)
- `sync_jobs.channel_id` → `data_channels.id` (CASCADE DELETE)

### Indexes

- `ix_regulatory_documents_publish_date`: 发布日期索引
- `ix_regulatory_documents_is_new`: 新文档标记索引
- `ix_regulatory_documents_is_read`: 已读状态索引
- `ix_sync_jobs_started_at`: 同步开始时间索引
- `ix_sync_jobs_status`: 同步状态索引

## Data Flow

```
DataSource (CDE)
    ↓
DataChannel (cde_domestic_guideline)
    ↓
RegulatoryDocument (640+ documents)
    ↓
SyncJob (backfill/daily_sync/manual_sync)
```

## Sample Data

### Data Sources
```json
{
  "code": "CDE",
  "name": "国家药品监督管理局药品审评中心",
  "base_url": "https://www.cde.org.cn"
}
```

### Data Channels
```json
{
  "code": "cde_domestic_guideline",
  "name": "国内药品技术指导原则",
  "list_url": "https://www.cde.org.cn/zdyz/listpage/9cd8db3b7530c6fa0c86485e563f93c7",
  "adapter_name": "CdeDomesticGuidelineAdapter"
}
```

### Regulatory Documents (Sample)
```json
{
  "document_id": "9c92f5cfa79fc44da0ac28d2b3a0f6b3",
  "title": "预防用mRNA疫苗临床试验技术指导原则（试行）",
  "publish_date": "2026-06-01",
  "status_text": "颁布",
  "classification": "生物制品",
  "original_url": "https://www.cde.org.cn/zdyz/domesticinfopage?zdyzIdCODE=9c92f5cfa79fc44da0ac28d2b3a0f6b3"
}
```

### Sync Jobs
```json
{
  "job_type": "backfill",
  "status": "success",
  "checked_count": 640,
  "new_count": 640,
  "updated_count": 0
}
```
