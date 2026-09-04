# PHASE1_REGULATORY_TRACKER

## Phase 1：CDE 国内药品技术指导原则法规监听系统

**版本：V1.0**

**状态：开发立项**

**目标：构建可持续运行的法规监听平台基础架构**

---

# 1. 项目背景

经过技术验证，已确认：

* Playwright 可以正常运行
* 页面驱动模式可以通过 CDE WAF
* 成功获取 `getDomesticGuideList`
* 成功获取真实分页数据
* 成功验证分页采集能力
* 已验证 MmEwMD 动态参数机制

验证结果表明：

> CDE 国内药品技术指导原则栏目具备稳定的数据采集能力。

---

# 2. 第一阶段目标

本阶段不建设完整法规情报平台。

仅建设：

```text
CDE 国内药品技术指导原则监听系统
```

实现：

```text
自动采集
↓
自动发现新增法规
↓
自动建立内部法规数据库
↓
前端展示法规动态
```

---

# 3. 第一阶段范围

## 纳入范围

数据源：

```text
CDE
└── 国内药品技术指导原则
```

功能：

* 历史数据初始化
* 增量同步
* 手动同步
* 法规数据库
* 去重机制
* 新法规识别
* 前端展示
* 原文链接跳转
* 同步日志

---

## 不纳入范围

以下内容后续阶段开发：

* NMPA
* CDE 发布通告
* CDE 征求意见稿
* ICH 指导原则
* 法规全文解析
* PDF下载
* AI问答
* RAG
* 向量数据库
* 邮件提醒
* 企业微信提醒
* 用户权限系统

---

# 4. 系统架构

```text
Frontend
    ↓
Backend API
    ↓
PostgreSQL

Crawler Worker
    ↓
Playwright
    ↓
CDE
```

---

## Frontend

负责：

* 法规列表
* 仪表盘统计
* 同步状态展示

禁止直接访问 CDE。

---

## Backend API

负责：

* 数据查询
* 数据统计
* 同步任务管理

---

## Crawler Worker

负责：

* Playwright采集
* 数据解析
* 数据入库

---

## PostgreSQL

负责：

* 法规存储
* 同步日志存储

---

# 5. 扩展架构设计

未来新增平台时：

```text
DataSource
├── CDE
├── NMPA
├── FDA
├── EMA
└── PMDA
```

新增栏目时：

```text
Channel
├── cde_domestic_guideline
├── cde_ich_guideline
├── cde_notice
├── nmpa_law
└── nmpa_announcement
```

新增平台只允许：

* 新增 Adapter
* 新增配置

禁止修改：

* 法规主表
* API结构
* 前端结构

---

# 6. 数据库设计

## data_sources

数据源表

字段：

```sql
id
code
name
base_url
enabled
created_at
updated_at
```

初始化：

```text
CDE
国家药品监督管理局药品审评中心
```

---

## data_channels

栏目表

字段：

```sql
id
source_id
code
name
list_url
adapter_name
enabled
created_at
updated_at
```

初始化：

```text
cde_domestic_guideline
国内药品技术指导原则
```

---

## regulatory_documents

法规主表

字段：

```sql
id

source_id
channel_id

source_code
channel_code

document_id

title

publish_date

status_text

classification

original_url

is_new

first_found_at

last_checked_at

created_at

updated_at

raw_data

unique_key
```

---

字段映射：

```text
document_id = zdyzIdCODE

title = title

publish_date = issueDate

status_text = nowstate

classification = fclass

original_url =
https://www.cde.org.cn/zdyz/domesticinfopage?zdyzIdCODE={zdyzIdCODE}
```

---

去重规则：

优先：

```text
document_id
```

备用：

```text
source_code
+
channel_code
+
title
+
publish_date
```

---

## sync_jobs

同步任务表

字段：

```sql
id

source_id
channel_id

job_type

started_at
finished_at

status

checked_count

new_count

updated_count

error_message

created_at
```

---

job_type：

```text
backfill
daily_sync
manual_sync
test
```

---

status：

```text
success
partial_failed
failed
```

---

# 7. 采集器设计

实现：

```text
CdeDomesticGuidelineAdapter
```

---

核心原则：

禁止：

```text
手动构造 MmEwMD

缓存 MmEwMD

硬编码接口
```

必须：

```text
页面生成 MmEwMD

页面触发接口

脚本监听接口结果
```

---

采集流程：

```text
打开页面

↓

等待页面加载

↓

监听 getDomesticGuideList

↓

获取 JSON

↓

解析 records

↓

翻页

↓

继续监听

↓

数据库写入
```

---

# 8. 同步策略

## 初始化同步

用途：

```text
首次部署
建立基础数据库
```

策略：

```text
抓取全部分页
```

当前预计：

```text
640+
64页
```

注意：

法规总数不得写死。

必须实时统计数据库记录数。

---

## 每日同步

时间：

```text
每天凌晨 02:00
```

策略：

```text
仅检查前3页
```

原因：

新增法规只会出现在最新分页。

无需每天全量扫描。

---

## 手动同步

前端按钮触发。

用途：

```text
立即检查是否有新增法规
```

---

# 9. 后端 API

## 仪表盘

```http
GET /api/regulatory-tracker/summary
```

返回：

```json
{
  "totalCount": 642,
  "todayNewCount": 2,
  "unreadNewCount": 5,
  "lastSyncTime": "2026-06-10 02:00:00",
  "lastSyncStatus": "success"
}
```

说明：

所有数据来自数据库实时统计。

禁止写死任何数量。

---

## 法规列表

```http
GET /api/regulatory-documents
```

支持：

* 关键词搜索
* 发布日期筛选
* 分类筛选
* 状态筛选
* 是否新增筛选
* 分页

---

## 标记已读

```http
PATCH /api/regulatory-documents/{id}/read
```

---

## 同步日志

```http
GET /api/sync-jobs
```

---

## 手动同步

```http
POST /api/sync-jobs/manual-sync
```

---

## 初始化同步

```http
POST /api/sync-jobs/backfill
```

---

# 10. 前端页面

页面名称：

```text
法规追踪
```

---

## 仪表盘

显示：

* 法规总数
* 今日新增
* 未读新增
* 最近同步时间
* 同步状态

---

## 筛选区域

支持：

* 关键词
* 发布日期
* 状态
* 分类
* 新增状态

---

## 法规列表

字段：

```text
平台
栏目
标题
状态
专业分类
发布日期
首次发现时间
原文链接
```

---

操作：

```text
打开原文
标记已读
```

---

## 同步日志

显示：

```text
开始时间
结束时间
新增数量
同步状态
错误信息
```

---

# 11. 首次部署要求

部署完成后必须自动执行：

```text
历史数据初始化
```

即：

```text
自动抓取全部64页

自动建立数据库

自动生成初始法规数据
```

因此：

新用户下载项目后：

```text
docker compose --env-file .env.local -f compose.dev.yml up -d
```

即可得到完整法规数据。

不允许出现空系统。

---

# 12. Docker部署要求

必须在工作区根目录提供：

```text
Dockerfile

compose.yml / compose.dev.yml

README.md

DEPLOYMENT.md

.env.example
```

---

环境变量：

```env
DATABASE_URL=

CDE_GUIDELINE_URL=https://www.cde.org.cn/zdyz/listpage/9cd8db3b7530c6fa0c86485e563f93c7

CRAWLER_HEADLESS=true

DAILY_SYNC_CRON=0 2 * * *
```

---

Playwright必须写入项目依赖。

禁止依赖开发者本机环境。

启动自动安装：

```bash
playwright install chromium
```

---

# 13. 错误处理

必须处理：

* Playwright启动失败
* 页面加载失败
* WAF失败
* 接口未触发
* JSON解析失败
* 翻页失败
* 数据库异常
* 同步中断

要求：

* 写入同步日志
* 前端可查看错误原因
* 支持重试

---

# 14. 验收标准

必须满足：

* 成功抓取第一页
* 成功抓取前三页
* 成功抓取全部历史数据
* document_id去重有效
* 新法规自动识别
* 自动建立数据库
* 每日自动同步
* 前端正常展示
* 原文链接可跳转
* 同步日志可查看
* Docker一键部署
* 新平台可扩展

---

# 15. Phase 2 预留规划

未来新增：

```text
CDE ICH指导原则

CDE 发布通告

CDE 征求意见稿

NMPA

FDA

EMA
```

新增要求：

```text
仅新增 Adapter

仅新增配置

不得修改现有数据库结构

不得修改前端展示逻辑

不得修改现有 API
```

本项目最终目标：

```text
建设统一法规监听平台

而非一次性采集脚本
```
