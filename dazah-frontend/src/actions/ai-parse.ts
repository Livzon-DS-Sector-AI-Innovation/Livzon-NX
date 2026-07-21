'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { revalidatePath } from 'next/cache'

const API_BASE_URL = getServerApiBaseUrl()

/**
 * AI解析实验记录文件
 * 支持解析：实验记录、工艺规程、批记录等
 */
export async function parseExperimentRecord(file: File, type: 'lab_confirmation' | 'scale_up'): Promise<any> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('parse_type', type)

  const response = await fetch(`${API_BASE_URL}/api/v1/ai/parse-experiment`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`解析失败: ${response.status} ${errorText}`)
  }

  const result = await response.json()
  revalidatePath('/rd/process-optimization')
  return result.data
}

/**
 * AI解析工艺参数
 * 从文本或文件中提取工艺参数
 */
export async function parseProcessParameters(content: string, type: 'lab_confirmation' | 'scale_up'): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/api/v1/ai/parse-parameters`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, parse_type: type }),
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`解析失败: ${response.status} ${errorText}`)
  }

  const result = await response.json()
  return result.data
}
