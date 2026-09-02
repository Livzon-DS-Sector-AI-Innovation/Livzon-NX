'use client'

// ====== 类型定义 ======
export interface SummaryStats {
  totalCount: number
  todayNewCount: number
  unreadNewCount: number
  lastSyncTime: string | null
  lastSyncStatus: string | null
}

export interface RegulatoryDocument {
  id: string
  sourceId: string
  channelId: string
  documentId: string
  title: string
  publishDate: string | null
  statusText: string | null
  classification: string | null
  originalUrl: string | null
  isNew: boolean
  isRead: boolean
  firstFoundAt: string
  lastCheckedAt: string | null
  createdAt: string
}

export interface SyncJob {
  id: string
  sourceId: string
  channelId: string
  jobType: string
  startedAt: string | null
  finishedAt: string | null
  status: string
  totalPages: number | null
  checkedCount: number
  newCount: number
  updatedCount: number
  errorMessage: string | null
  createdAt: string
}

export interface DocumentListParams {
  keyword?: string
  publishDateFrom?: string
  publishDateTo?: string
  statusText?: string
  classification?: string
  isNew?: boolean
  page?: number
  pageSize?: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
  totalPages: number
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}


// ====== AI 分析类型 ======
export interface AIAnalysisResult {
  documentId: string
  documentTitle: string
  impactLevel: 'high' | 'medium' | 'low' | 'none'
  impactScore: number // 0-100
  impactSummary: string
  keyChanges: string[]
  impactAreas: string[]
  complianceSuggestions: string[]
  timelineUrgency: 'urgent' | 'normal' | 'long_term'
  generatedAt: string
}

export interface AIBatchAnalysisResult {
  totalAnalyzed: number
  highImpact: number
  mediumImpact: number
  lowImpact: number
  noneImpact: number
  topConcerns: Array<{
    title: string
    documentId: string
    impactLevel: 'high' | 'medium' | 'low' | 'none'
    reason: string
  }>
  overallAssessment: string
  generatedAt: string
}


// ====== API 调用 ======
export async function fetchSummary(): Promise<SummaryStats> {
  const res = await fetch(`/api/v1/regulatory-tracker/summary`)
  const json: ApiResponse<SummaryStats> = await res.json()
  return json.data
}

export async function fetchDocuments(
  params: DocumentListParams = {}
): Promise<PaginatedResponse<RegulatoryDocument>> {
  const searchParams = new URLSearchParams()
  
  if (params.keyword) searchParams.append('keyword', params.keyword)
  if (params.publishDateFrom) searchParams.append('publishDateFrom', params.publishDateFrom)
  if (params.publishDateTo) searchParams.append('publishDateTo', params.publishDateTo)
  if (params.statusText) searchParams.append('statusText', params.statusText)
  if (params.classification) searchParams.append('classification', params.classification)
  if (params.isNew !== undefined) searchParams.append('isNew', params.isNew.toString())
  if (params.page) searchParams.append('page', params.page.toString())
  if (params.pageSize) searchParams.append('pageSize', params.pageSize.toString())

  const url = `/api/v1/regulatory-documents?${searchParams.toString()}`
  const res = await fetch(url)
  const json: ApiResponse<PaginatedResponse<RegulatoryDocument>> = await res.json()
  return json.data
}


export async function fetchSyncJobs(
  page: number = 1,
  pageSize: number = 20
): Promise<PaginatedResponse<SyncJob>> {
  const url = `/api/v1/sync-jobs?page=${page}&pageSize=${pageSize}`
  const res = await fetch(url)
  const json: ApiResponse<PaginatedResponse<SyncJob>> = await res.json()
  return json.data
}


// ====== AI 分析 API（当前为 mock，未来替换为真实接口） ======

/**
 * 单条文档 AI 分析
 * 当前返回基于规则引擎的 mock 结果，未来将调用后端 LLM 接口
 */
export async function fetchAIAnalysis(
  doc: RegulatoryDocument
): Promise<AIAnalysisResult> {
  // 调用后端 AI 分析接口
  const res = await fetch(`/api/v1/regulatory-documents/${doc.id}/analyze`, { method: 'POST' })
  const json = await res.json()
  
  if (json.code !== 200) {
    throw new Error(json.message || 'AI 分析失败')
  }
  
  // 从后端获取分析结果后，重新获取文档数据
  const docRes = await fetch(`/api/v1/regulatory-documents?page=1&pageSize=100`)
  const docJson = await docRes.json()
  const updatedDoc = docJson.data.items.find((d: { id: string }) => d.id === doc.id)
  
  if (!updatedDoc || !updatedDoc.aiSummary) {
    // 如果还没有分析结果，返回默认值
    return {
      documentId: doc.id,
      documentTitle: doc.title,
      impactLevel: 'low',
      impactScore: 30,
      impactSummary: 'AI 分析尚未完成，请稍后重试',
      keyChanges: [],
      impactAreas: [],
      complianceSuggestions: [],
      timelineUrgency: 'long_term',
      generatedAt: new Date().toISOString(),
    }
  }
  
  // 根据 AI 分析结果构建前端展示数据
  const relevanceScore = updatedDoc.aiRelevanceScore || 0.5
  const impactLevel = relevanceScore >= 0.7 ? 'high' : relevanceScore >= 0.4 ? 'medium' : relevanceScore >= 0.1 ? 'low' : 'none'
  const impactScore = Math.round(relevanceScore * 100)
  
  return {
    documentId: doc.id,
    documentTitle: doc.title,
    impactLevel,
    impactScore,
    impactSummary: updatedDoc.aiSummary || '无摘要',
    keyChanges: updatedDoc.aiKeyPoints || [],
    impactAreas: ['化学原料药'],
    complianceSuggestions: ['根据 AI 分析结果评估合规性'],
    timelineUrgency: relevanceScore >= 0.7 ? 'urgent' : relevanceScore >= 0.4 ? 'normal' : 'long_term',
    generatedAt: updatedDoc.aiAnalyzedAt || new Date().toISOString(),
  }
}

/**
 * 批量文档 AI 分析（化学原料药视角）
 * 当前返回基于规则引擎的 mock 结果，未来将调用后端 LLM 接口
 */
export async function fetchAIBatchAnalysis(
  docs: RegulatoryDocument[]
): Promise<AIBatchAnalysisResult> {
  // 调用后端批量 AI 分析接口
  const res = await fetch(`/api/v1/regulatory-documents/analyze?limit=${docs.length}`, { method: 'POST' })
  const json = await res.json()
  
  if (json.code !== 200) {
    throw new Error(json.message || 'AI 批量分析失败')
  }
  
  // 重新获取文档列表以获取 AI 分析结果
  const docRes = await fetch(`/api/v1/regulatory-documents?page=1&pageSize=100`)
  const docJson = await docRes.json()
  const updatedDocs: Array<{ id: string; title: string; aiRelevanceScore?: number; aiSummary?: string; aiKeyPoints?: string[]; aiAnalyzedAt?: string }> = docJson.data.items
  
  // 为每个文档构建分析结果
  const analyses = updatedDocs.map((doc) => {
    const relevanceScore = doc.aiRelevanceScore || 0.5
    const impactLevel: 'high' | 'medium' | 'low' | 'none' = relevanceScore >= 0.7 ? 'high' : relevanceScore >= 0.4 ? 'medium' : relevanceScore >= 0.1 ? 'low' : 'none'
    const impactScore = Math.round(relevanceScore * 100)
    
    return {
      documentId: doc.id,
      documentTitle: doc.title,
      impactLevel,
      impactScore,
      impactSummary: doc.aiSummary || '无摘要',
      keyChanges: doc.aiKeyPoints || [],
      impactAreas: ['化学原料药'],
      complianceSuggestions: ['根据 AI 分析结果评估合规性'],
      timelineUrgency: relevanceScore >= 0.7 ? 'urgent' : relevanceScore >= 0.4 ? 'normal' : 'long_term',
      generatedAt: doc.aiAnalyzedAt || new Date().toISOString(),
    }
  })
  const highImpact = analyses.filter((a) => a.impactLevel === 'high').length
  const mediumImpact = analyses.filter((a) => a.impactLevel === 'medium').length
  const lowImpact = analyses.filter((a) => a.impactLevel === 'low').length
  const noneImpact = analyses.filter((a) => a.impactLevel === 'none').length

  const topConcerns = analyses
    .filter((a) => a.impactLevel === 'high' || a.impactLevel === 'medium')
    .sort((a, b) => b.impactScore - a.impactScore)
    .slice(0, 5)
    .map((a) => ({
      title: a.documentTitle,
      documentId: a.documentId,
      impactLevel: a.impactLevel,
      reason: a.impactSummary,
    }))

  const total = analyses.length
  const overallAssessment = highImpact > 0
    ? `在 ${total} 条法规中，有 ${highImpact} 条对化学原料药业务存在重大影响，建议优先评估并制定应对方案。`
    : mediumImpact > 0
    ? `在 ${total} 条法规中，有 ${mediumImpact} 条对化学原料药业务存在中等影响，建议组织技术团队重点研读。`
    : `在 ${total} 条法规中，未发现对化学原料药业务有重大影响的法规，建议保持常规关注。`

  return {
    totalAnalyzed: total,
    highImpact,
    mediumImpact,
    lowImpact,
    noneImpact,
    topConcerns,
    overallAssessment,
    generatedAt: new Date().toISOString(),
  }
}
