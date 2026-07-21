# API 架构重构追踪

## 问题描述

根据 AGENTS.md 规范，所有写操作（POST/PUT/DELETE）应该使用 Server Actions，写在 `actions/` 目录。
但目前有 96 个 mutation 函数在 `lib/api/` 中被 Client Components 直接调用，违反了架构规范。

## 规范对比

**AGENTS.md 要求：**
- ✅ 客户端读操作：`lib/api/*.ts` 使用相对路径 `/api/v1/...`
- ✅ 服务器端读操作：`actions/*.ts` 使用 `API_BASE_URL`
- ✅ 写操作：必须在 `actions/` 目录，使用 Server Actions
- ❌ 当前问题：写操作在 `lib/api/` 中被 Client Components 直接调用

## 重构计划

按模块逐个重构，从简单到复杂：

### Phase 1: 单 mutation 模块
- [x] `regulatory-tracker-client` (1 mutation) - ✅ 已完成
- [x] `ai` (2 mutations) - ✅ 已完成

### Phase 2: 小型模块（3-5 mutations）
- [ ] `registration-client` (3 mutations) - 待重构
- [ ] `label-verification` (3 mutations) - 待重构
- [ ] `registration` (4 mutations) - 待重构
- [ ] `research` (5 mutations) - 待重构

### Phase 3: 中型模块（8-13 mutations）
- [ ] `quality-cpv` (8 mutations) - 待重构
- [ ] `energy` (8 mutations) - 待重构
- [ ] `hr` (13 mutations) - 待重构
- [ ] `dossier-writer-client` (13 mutations) - 待重构

### Phase 4: 大型模块（27+ mutations）
- [ ] `quality` (27 mutations) - 待重构

## 重构模式

### 步骤 1: 移动函数到 actions/
```typescript
// Before: lib/api/module-client.ts
export async function createSomething(data: CreateInput) {
  const res = await fetch('/api/v1/module/something', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  return res.json()
}

// After: actions/module.ts
'use server'
import { revalidatePath } from 'next/cache'

const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:8000'

export async function createSomething(data: CreateInput) {
  const res = await fetch(`${API_BASE_URL}/api/v1/module/something`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('创建失败')
  revalidatePath('/module')
  return res.json()
}
```

### 步骤 2: 更新 Client Components
```typescript
// Before
import { createSomething } from '@/lib/api/module-client'

// After
import { createSomething } from '@/actions/module'
```

### 步骤 3: 保留 fetch 函数在 lib/api/
只保留 `fetch*` 开头的读操作函数，删除 mutation 函数。

## 特殊处理

### 文件上传
```typescript
// actions/module.ts
export async function uploadFile(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  
  const res = await fetch(`${API_BASE_URL}/api/v1/module/upload`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) throw new Error('上传失败')
  revalidatePath('/module')
  return res.json()
}
```

### 流式响应
```typescript
// lib/api/module.ts (保留在 lib/api/)
export async function streamResponse(
  onChunk: (text: string) => void,
  onDone: () => void,
) {
  // 流式响应必须保留在客户端
  const res = await fetch('/api/v1/module/stream')
  // ... 处理流
}
```

## 进度记录

### 2026-06-20: 完成 ai 模块重构
- 创建 `actions/ai.ts`
- 移动 `generateExamQuestions` 和 `exportExam` 到 Server Actions
- 更新 `components/hr/AiExamClient.tsx` 的导入
- 从 `lib/api/ai.ts` 删除 mutation 函数
- 保留 `streamChat` 流式响应函数（必须保留在客户端）
- 验证构建成功

### 2026-06-18: 完成 regulatory-tracker-client 重构
- 创建 `actions/regulatory-tracker.ts`
- 移动 `markDocumentRead` 函数到 Server Action
- 更新 `registration/regulation/page.tsx` 的导入
- 从 `lib/api/regulatory-tracker-client.ts` 删除 mutation 函数
- 验证构建成功

### 2026-06-18: 开始重构
- 创建追踪文档
- 识别 96 个需要重构的 mutation 函数
- 制定分阶段重构计划

---

## 待办事项

- [x] 完成 `regulatory-tracker-client` 重构
- [x] 完成 `ai` 重构
- [ ] 完成 `registration-client` 重构
- [ ] 完成 `label-verification` 重构
- [ ] 完成 `registration` 重构
- [ ] 完成 `research` 重构
- [ ] 完成 `quality-cpv` 重构
- [ ] 完成 `energy` 重构
- [ ] 完成 `hr` 重构
- [ ] 完成 `dossier-writer-client` 重构
- [ ] 完成 `quality` 重构
- [ ] 更新 AGENTS.md 添加重构完成说明
