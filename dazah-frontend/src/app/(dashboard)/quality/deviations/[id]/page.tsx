import { getServerApiBaseUrl } from '@/lib/server-api'
import { DeviationDetail } from '@/components/quality'
import { updateFeishuDeviationLedgerRecord as updateDeviationAction } from '@/actions/quality'
import type { FeishuDeviationLedgerRecordItem } from '@/types/quality'
import { redirect } from 'next/navigation'

export const dynamic = 'force-dynamic'

const API_BASE_URL = getServerApiBaseUrl()

async function getInitialDeviationDetail(id: string): Promise<{
  deviation: FeishuDeviationLedgerRecordItem | null
  loadError: string | null
}> {
  try {
    const detailResponse = await fetch(`${API_BASE_URL}/api/v1/quality/deviation-ledger-records/${id}`, {
      cache: 'no-store',
    })
    if (!detailResponse.ok) {
      throw new Error(`请求失败: ${detailResponse.status} ${detailResponse.statusText}`)
    }
    const detailJson = await detailResponse.json()
    return {
      deviation: detailJson.data || null,
      loadError: null,
    }
  } catch (error) {
    return {
      deviation: null,
      loadError: error instanceof Error ? error.message : '加载失败',
    }
  }
}

export default async function DeviationDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const { id } = await params
  const resolvedSearchParams = await searchParams
  const { deviation, loadError } = await getInitialDeviationDetail(id)

  async function saveAction(formData: FormData) {
    'use server'

    const getText = (key: string) => {
      const value = formData.get(key)
      if (typeof value !== 'string') return null
      const normalized = value.trim()
      return normalized || null
    }

    const getBoolean = (key: string) => {
      const value = getText(key)
      if (value === 'true') return true
      if (value === 'false') return false
      return null
    }

    await updateDeviationAction(id, {
      title: getText('description') || '',
      description: getText('description'),
      affected_items: getText('affected_items'),
      has_occurred_before: getBoolean('has_occurred_before'),
      root_cause_analysis: getText('root_cause_analysis'),
      level: getText('level') as FeishuDeviationLedgerRecordItem['level'],
      investigation_completed_at: getText('investigation_completed_at')
        ? new Date(getText('investigation_completed_at') as string).toISOString()
        : null,
      corrective_actions: getText('corrective_actions'),
      material_disposition: getText('material_disposition'),
      is_closed: getBoolean('is_closed'),
      close_time: getText('close_time')
        ? new Date(getText('close_time') as string).toISOString()
        : null,
    })

    redirect(`/quality/deviations/${id}`)
  }

  const editParam = resolvedSearchParams.edit
  const initialEditMode = Array.isArray(editParam) ? editParam.includes('1') : editParam === '1'

  return (
    <DeviationDetail
      initialDeviation={deviation}
      initialLoadError={loadError}
      initialEditMode={initialEditMode}
      saveAction={saveAction}
    />
  )
}
