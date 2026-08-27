import { DeviationDetail, QualityQueryProvider } from '@/components/quality'
import { updateDeviation } from '@/actions/quality-deviation'
import type { DeviationLevel } from '@/types/quality'
import type { DeviationDetail as DeviationDetailType } from '@/types/quality'
import { fetchDeviationServer } from '@/lib/api/server/quality'
import { redirect } from 'next/navigation'

export const dynamic = 'force-dynamic'

async function getInitialDeviationDetail(id: string): Promise<{
  deviation: DeviationDetailType | null
  loadError: string | null
}> {
  try {
    const deviation = await fetchDeviationServer(id)
    return {
      deviation: deviation as DeviationDetailType | null,
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

    await updateDeviation(id, {
      title: getText('description') || '',
      description: getText('description'),
      affected_items: getText('affected_items'),
      has_occurred_before: getBoolean('has_occurred_before'),
      root_cause_analysis: getText('root_cause_analysis'),
      level: getText('level') as DeviationLevel | null,
      investigation_completed_at: getText('investigation_completed_at')
        ? new Date(getText('investigation_completed_at') as string).toISOString()
        : null,
      corrective_actions: getText('corrective_actions'),
      material_disposition: getText('material_disposition'),
    })

    redirect(`/quality/deviations/${id}`)
  }

  const editParam = resolvedSearchParams.edit
  const initialEditMode = Array.isArray(editParam) ? editParam.includes('1') : editParam === '1'

  return (
    <QualityQueryProvider>
      <DeviationDetail
        initialDeviation={deviation}
        initialLoadError={loadError}
        initialEditMode={initialEditMode}
        saveAction={saveAction}
      />
    </QualityQueryProvider>
  )
}
