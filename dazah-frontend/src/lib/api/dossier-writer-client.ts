'use client'

import type {
  ProductDossier,
  ProductDossierCreate,
  ProductDossierUpdate,
  Chapter,
  ChapterDetail,
  ChapterAsset,
  ParseResult,
  ExportResult,
  PaginatedResponse,
} from '@/types/dossier-writer'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

const headers = { 'Content-Type': 'application/json' }

// ====== Product Dossier ======

export async function fetchProductDossiers(
  skip: number = 0,
  limit: number = 100
): Promise<PaginatedResponse<ProductDossier>> {
  const res = await fetch(
    `/api/v1/dossier-writer/products?skip=${skip}&limit=${limit}`
  )
  const json: ApiResponse<PaginatedResponse<ProductDossier>> = await res.json()
  return json.data
}

export async function fetchProductDossier(id: string): Promise<ProductDossier> {
  const res = await fetch(`/api/v1/dossier-writer/products/${id}`)
  const json: ApiResponse<ProductDossier> = await res.json()
  return json.data
}

export async function createProductDossier(
  data: ProductDossierCreate
): Promise<ProductDossier> {
  const res = await fetch(`/api/v1/dossier-writer/products`, {
    method: 'POST',
    headers,
    body: JSON.stringify(data),
  })
  const json: ApiResponse<ProductDossier> = await res.json()
  
  if (json.code !== 200) {
    throw new Error(json.message || '创建失败')
  }
  
  return json.data
}

export async function updateProductDossier(
  id: string,
  data: ProductDossierUpdate
): Promise<ProductDossier> {
  const res = await fetch(`/api/v1/dossier-writer/products/${id}`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(data),
  })
  const json: ApiResponse<ProductDossier> = await res.json()
  return json.data
}

export async function deleteProductDossier(id: string): Promise<void> {
  await fetch(`/api/v1/dossier-writer/products/${id}`, {
    method: 'DELETE',
  })
}

// ====== Template Upload ======

export interface UploadResult {
  file_id?: string
  filename: string
  file_path?: string
  file_size?: number
  status: 'success' | 'failed'
  error?: string
}

export interface UploadResponse {
  results: UploadResult[]
  success_count: number
  failed_count: number
  matched_count?: number
  unmatched_files?: string[]
}

export async function uploadTemplates(
  dossierId: string,
  files: File[]
): Promise<UploadResponse> {
  const formData = new FormData()
  files.forEach(file => formData.append('files', file))

  const res = await fetch(
    `/api/v1/dossier-writer/products/${dossierId}/templates`,
    {
      method: 'POST',
      body: formData,
    }
  )
  const json: ApiResponse<UploadResponse> = await res.json()
  
  if (json.code !== 200) {
    throw new Error(json.message || '上传失败')
  }
  
  return json.data
}

// ====== Template Parsing ======

export async function parseTemplates(dossierId: string): Promise<ParseResult> {
  const res = await fetch(
    `/api/v1/dossier-writer/products/${dossierId}/parse`,
    { method: 'POST' }
  )
  const json: ApiResponse<ParseResult> = await res.json()
  
  if (json.code !== 200) {
    throw new Error(json.message || '解析失败')
  }
  
  return json.data
}

// ====== Chapter ======

export async function fetchChapterTree(dossierId: string): Promise<Chapter[]> {
  const res = await fetch(
    `/api/v1/dossier-writer/products/${dossierId}/chapters`
  )
  const json: ApiResponse<Chapter[]> = await res.json()
  return json.data
}

export async function fetchChapterDetail(chapterId: string): Promise<ChapterDetail> {
  const res = await fetch(
    `/api/v1/dossier-writer/chapters/${chapterId}`
  )
  const json: ApiResponse<ChapterDetail> = await res.json()
  return json.data
}

// ====== Asset ======

export async function uploadChapterAsset(
  chapterId: string,
  files: File[]
): Promise<{ assets: ChapterAsset[]; count: number }> {
  const formData = new FormData()
  files.forEach(file => formData.append('files', file))

  const res = await fetch(
    `/api/v1/dossier-writer/chapters/${chapterId}/assets`,
    {
      method: 'POST',
      body: formData,
    }
  )
  const json: ApiResponse<{ assets: ChapterAsset[]; count: number }> = await res.json()
  return json.data
}

export async function fetchChapterAssets(chapterId: string): Promise<ChapterAsset[]> {
  const res = await fetch(
    `/api/v1/dossier-writer/chapters/${chapterId}/assets`
  )
  const json: ApiResponse<ChapterAsset[]> = await res.json()
  return json.data
}

export async function deleteChapterAsset(assetId: string): Promise<void> {
  const res = await fetch(`/api/v1/dossier-writer/assets/${assetId}`, {
    method: 'DELETE',
  })
  const json = await res.json()
  if (json.code !== 200) {
    throw new Error(json.message || '删除失败')
  }
}

// ====== Export ======

export async function exportDossier(
  dossierId: string,
  chapterIds?: string[]
): Promise<ExportResult> {
  const res = await fetch(
    `/api/v1/dossier-writer/products/${dossierId}/export`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify({ chapter_ids: chapterIds || null, format: 'docx' }),
    }
  )
  const json: ApiResponse<ExportResult> = await res.json()
  
  if (json.code !== 200) {
    throw new Error(json.message || '导出失败')
  }
  
  return json.data
}

export function getDownloadUrl(dossierId: string, filename: string): string {
  return `/api/v1/dossier-writer/products/${dossierId}/download?filename=${encodeURIComponent(filename)}`
}


// ====== Chapter Preview ======

export interface ChapterPreview {
  success: boolean
  chapter_code: string
  chapter_title: string
  paragraphs: Array<{ text: string; style: string }>
  tables: string[][][]
  message?: string
}

export async function getChapterPreview(chapterId: string): Promise<ChapterPreview> {
  const res = await fetch(
    `/api/v1/dossier-writer/chapters/${chapterId}/preview`
  )
  const json: ApiResponse<ChapterPreview> = await res.json()
  
  if (json.code !== 200) {
    throw new Error(json.message || '获取预览失败')
  }
  
  return json.data
}

// ====== Asset Matching ======

export interface MatchResult {
  success: boolean
  message: string
  matched_count: number
  unmatched_files: string[]
}

export async function matchAssetsToChapters(dossierId: string): Promise<MatchResult> {
  const res = await fetch(
    `/api/v1/dossier-writer/products/${dossierId}/match-assets`,
    { method: 'POST' }
  )
  const json: ApiResponse<MatchResult> = await res.json()
  
  if (json.code !== 200) {
    throw new Error(json.message || '匹配失败')
  }
  
  return json.data
}


// ====== Field Filling ======

export interface FieldFillResult {
  success: boolean
  message: string
  filled_count: number
  total_fields: number
  results: Array<{
    field_name: string
    status: string
    filled_value: string | null
  }>
}

export async function fillChapterFields(chapterId: string): Promise<FieldFillResult> {
  const res = await fetch(
    `/api/v1/dossier-writer/chapters/${chapterId}/fill-fields`,
    { method: 'POST' }
  )
  const json: ApiResponse<FieldFillResult> = await res.json()
  
  if (json.code !== 200) {
    throw new Error(json.message || '填充失败')
  }
  
  return json.data
}


// ====== AI Fill ======

import type {
  AssetCategory,
  AIPreviewResult,
  AIConfirmRequest,
  AIFillResult,
  PageSplitPreviewResult,
} from '@/types/dossier-writer'

export async function fetchAssetCategories(chapterCode: string): Promise<AssetCategory[]> {
  const res = await fetch(
    `/api/v1/dossier-writer/chapters/${chapterCode}/asset-categories`
  )
  const json: ApiResponse<AssetCategory[]> = await res.json()
  if (json.code !== 200) {
    throw new Error(json.message || '获取素材分类失败')
  }
  return json.data
}

export async function aiPreviewExtraction(chapterId: string): Promise<AIPreviewResult> {
  const res = await fetch(
    `/api/v1/dossier-writer/chapters/${chapterId}/ai-preview`,
    { method: 'POST' }
  )
  const json: ApiResponse<AIPreviewResult> = await res.json()
  if (json.code !== 200) {
    throw new Error(json.message || 'AI 解析失败')
  }
  return json.data
}

export async function aiConfirmAndFill(
  chapterId: string,
  data: AIConfirmRequest
): Promise<AIFillResult> {
  const res = await fetch(
    `/api/v1/dossier-writer/chapters/${chapterId}/ai-confirm`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify(data),
    }
  )
  const json: ApiResponse<AIFillResult> = await res.json()
  if (json.code !== 200) {
    throw new Error(json.message || '填充失败')
  }
  return json.data
}

export async function splitPreview(
  assetId: string,
  availableAppendixSlots: string[]
): Promise<PageSplitPreviewResult> {
  const res = await fetch(
    `/api/v1/dossier-writer/assets/${assetId}/split-preview`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify({ available_appendix_slots: availableAppendixSlots }),
    }
  )
  const json: ApiResponse<PageSplitPreviewResult> = await res.json()
  if (json.code !== 200) {
    throw new Error(json.message || '拆分预览失败')
  }
  return json.data
}

export async function splitConfirmAndInsert(
  chapterId: string,
  splits: Array<{
    split_id: string
    appendix_slot: string
    asset_id: string
    page_number: number
  }>
): Promise<{ success: boolean; message: string; inserted_count: number }> {
  const res = await fetch(
    `/api/v1/dossier-writer/chapters/${chapterId}/split-confirm`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify({ splits }),
    }
  )
  const json: ApiResponse<{ success: boolean; message: string; inserted_count: number }> = await res.json()
  if (json.code !== 200) {
    throw new Error(json.message || '拆分确认失败')
  }
  return json.data
}

// ====== Chapter Docx File ======

export function getChapterDocxUrl(chapterId: string): string {
  return `/api/v1/dossier-writer/chapters/${chapterId}/docx-file`
}

export async function fetchChapterDocx(chapterId: string): Promise<ArrayBuffer | null> {
  try {
    // Add cache-busting timestamp to avoid browser caching
    const url = `/api/v1/dossier-writer/chapters/${chapterId}/docx-file?t=${Date.now()}`
    const res = await fetch(url, {
      cache: 'no-cache',
      headers: {
        'Cache-Control': 'no-cache',
      },
    })
    if (!res.ok) return null
    return await res.arrayBuffer()
  } catch {
    return null
  }
}

// ====== Asset Category ======

export async function updateAssetCategory(
  assetId: string,
  categoryId: string | null
): Promise<{ id: string; category_id: string | null }> {
  const res = await fetch(
    `/api/v1/dossier-writer/assets/${assetId}`,
    {
      method: 'PATCH',
      headers,
      body: JSON.stringify({ category_id: categoryId }),
    }
  )
  const json = await res.json()
  if (json.code !== 200) {
    throw new Error(json.message || '更新分类失败')
  }
  return json.data
}
