'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { revalidatePath } from 'next/cache'

const API_BASE_URL = getServerApiBaseUrl()

/**
 * 标记法规文档为已读
 */
export async function markDocumentRead(id: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/v1/regulatory-documents/${id}/read`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
  })
  
  if (!res.ok) {
    throw new Error(`标记已读失败: ${res.status} ${res.statusText}`)
  }
  
  revalidatePath('/registration/regulation')
}
