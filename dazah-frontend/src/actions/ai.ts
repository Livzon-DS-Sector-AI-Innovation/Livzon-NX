'use server'

import { getAuthHeaders } from '@/lib/auth'
import { getServerApiBaseUrl } from '@/lib/server-api'
import { ExamGenerateResponse, ExamExportData } from '@/types/hr'

const API_BASE_URL = getServerApiBaseUrl()

async function requireAuthHeader(): Promise<Record<string, string>> {
  const headers = await getAuthHeaders()
  if (!headers.Authorization) {
    throw new Error('未登录或登录已过期')
  }
  return { Authorization: headers.Authorization }
}

export async function generateExamQuestions(file: File): Promise<ExamGenerateResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const res = await fetch(`${API_BASE_URL}/api/v1/ai/exam/generate`, {
    method: 'POST',
    headers: await requireAuthHeader(),
    body: formData,
  })

  if (!res.ok) {
    throw new Error(`出题失败（${res.status}）`)
  }

  return res.json()
}

export async function exportExam(data: ExamExportData): Promise<Blob> {
  const res = await fetch(`${API_BASE_URL}/api/v1/ai/exam/export`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(await requireAuthHeader()),
    },
    body: JSON.stringify(data),
  })

  if (!res.ok) {
    throw new Error(`导出失败（${res.status}）`)
  }

  return res.blob()
}
