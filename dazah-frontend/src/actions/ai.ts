'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { ExamGenerateResponse, ExamExportData } from '@/types/hr'

const API_BASE_URL = getServerApiBaseUrl()

export async function generateExamQuestions(file: File): Promise<ExamGenerateResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const res = await fetch(`${API_BASE_URL}/api/v1/ai/exam/generate`, {
    method: 'POST',
    body: formData,
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(`出题失败: ${res.status} ${text}`)
  }

  return res.json()
}

export async function exportExam(data: ExamExportData): Promise<Blob> {
  const res = await fetch(`${API_BASE_URL}/api/v1/ai/exam/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(`导出失败: ${res.status} ${text}`)
  }

  return res.blob()
}
