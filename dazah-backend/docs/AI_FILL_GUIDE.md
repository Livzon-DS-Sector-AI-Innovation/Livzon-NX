# AI 智能填充功能指南

## 功能概述

AI 智能填充功能用于自动从上传的素材文档中提取结构化字段值，并填充到申报资料模板中。相比传统的硬编码规则方案，AI 方案具有以下优势：

- **品种无关**：更换品种无需修改代码或配置
- **容错性强**：模板措辞变化、表格顺序变化都能正确匹配
- **操作简便**：用户只需上传素材，AI 自动完成提取和填充

## 系统架构

```
用户上传素材 → 选择素材分类
     ↓
AI 文本提取（docx/doc/pdf → 纯文本）
     ↓
LLM 字段提取（按分类路由，提取结构化值）
     ↓
用户预览确认（可修改提取结果）
     ↓
AI 位置定位（确定填充到模板的哪个位置）
     ↓
写入文档（更新 working copy）
```

## 配置 DeepSeek API

### 1. 获取 API Key

访问 [DeepSeek 开放平台](https://platform.deepseek.com/) 注册并获取 API Key。

### 2. 配置环境变量

编辑 `dazah-backend/.env` 文件，填入你的 API Key：

```env
# LLM Configuration (DeepSeek)
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

### 3. 重启后端服务

```bash
# 停止当前服务
pkill -f "uvicorn.*dazah"

# 重新启动
cd dazah-backend
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 使用流程

### 步骤 1：获取素材分类

```bash
GET /api/v1/dossier-writer/chapters/{chapter_code}/asset-categories
```

返回该章节需要的素材分类列表，例如 S.6 包含：
- 原料药质量标准
- 包材质量标准
- 授权书
- 包材相关证明材料（多合一 PDF）
- 厂家报告单
- 验证研究资料

### 步骤 2：上传素材并选择分类

用户在前端上传素材文件时，需要选择对应的分类。前端根据分类过滤素材，减少 AI 的处理范围。

### 步骤 3：AI 解析预览

```bash
POST /api/v1/dossier-writer/chapters/{chapter_id}/ai-preview
```

AI 会从素材中提取字段值，返回预览结果供用户确认：

```json
{
  "fields": [
    {
      "field_name": "包装形式",
      "value": "药用铝瓶I+包装外袋+包装泡沫III+中性纸箱III",
      "confidence": 0.95,
      "source": "头孢噻肟钠质量标准.doc - 段落[34]"
    },
    {
      "field_name": "包材类型",
      "value": "药用铝瓶Ⅰ",
      "confidence": 0.92,
      "source": "药用铝瓶质量标准.docx - 表格[0]"
    }
  ],
  "token_usage": {
    "prompt_tokens": 3500,
    "completion_tokens": 800,
    "total_tokens": 4300
  }
}
```

### 步骤 4：用户确认并填充

用户在前端确认或修改提取结果后，调用确认接口：

```bash
POST /api/v1/dossier-writer/chapters/{chapter_id}/ai-confirm
Content-Type: application/json

{
  "fields": [
    {
      "field_name": "包装形式",
      "value": "药用铝瓶I+包装外袋+包装泡沫III+中性纸箱III",
      "field_mapping_id": "xxx-xxx-xxx"
    }
  ]
}
```

系统会将确认后的值写入文档。

## 多页 PDF 拆分

对于包含多种内容的合并 PDF（如营业执照、CDE公示、检验报告单都在一个文件中），系统会自动按页拆分识别。

### 拆分预览

```bash
POST /api/v1/dossier-writer/assets/{asset_id}/split-preview
Content-Type: application/json

{
  "available_appendix_slots": ["附录1", "附录2", "附录3", "附录4", "附录5"]
}
```

返回每页的识别结果：

```json
{
  "pages": [
    {
      "page_number": 1,
      "page_type": "厂内检验报告单",
      "content_summary": "药用铝瓶I检验报告，批号230706001",
      "appendix_slot": "附录5"
    },
    {
      "page_number": 3,
      "page_type": "营业执照",
      "content_summary": "石家庄市华辰包装有限公司营业执照",
      "appendix_slot": "附录1"
    }
  ]
}
```

### 拆分确认并插入

```bash
POST /api/v1/dossier-writer/chapters/{chapter_id}/split-confirm
Content-Type: application/json

{
  "splits": [
    {
      "split_id": "xxx",
      "appendix_slot": "附录1",
      "asset_id": "xxx",
      "page_number": 3
    }
  ]
}
```

## Token 消耗估算

以 S.6 章节为例：

| 操作 | 输入 Token | 输出 Token | 费用（约） |
|------|-----------|-----------|-----------|
| 字段提取 | ~3500 | ~800 | ¥0.02 |
| 位置定位 | ~2000 | ~600 | ¥0.01 |
| 页面拆分 | ~1500 | ~400 | ¥0.01 |
| **合计** | **~7000** | **~1800** | **¥0.04** |

## 故障排查

### 问题 1：LLM 服务未配置

**现象**：调用 AI 预览接口返回 "LLM 服务未配置"

**解决**：
1. 检查 `.env` 文件中的 `LLM_API_KEY` 是否已填写真实值
2. 确认后端服务已重启（环境变量需要重启后生效）

### 问题 2：AI 提取结果不准确

**现象**：提取的字段值与素材内容不符

**解决**：
1. 检查素材分类是否正确选择
2. 确认素材文档格式支持（docx/doc/pdf）
3. 查看 `source` 字段，确认 AI 是从正确的素材中提取的
4. 如仍不准确，可在确认界面手动修改

### 问题 3：API 调用超时

**现象**：请求超时或返回 504

**解决**：
1. DeepSeek API 可能偶尔响应慢，可重试
2. 检查网络连接
3. 考虑使用本地部署的 LLM（如 Ollama + Qwen）

## 支持的 LLM 服务

当前系统使用 OpenAI 兼容 API 格式，支持以下服务：

- **DeepSeek**（推荐，性价比高）
- **OpenAI**（GPT-4o 等）
- **通义千问**（阿里云）
- **本地部署**（Ollama + Qwen/Llama）

只需修改 `.env` 中的 `LLM_BASE_URL` 和 `LLM_API_KEY` 即可切换。

## 下一步

- 前端界面开发（分类上传 + 预览确认）
- 其他章节（S.1~S.5, S.7）的配置扩展
- 批量导出功能优化
