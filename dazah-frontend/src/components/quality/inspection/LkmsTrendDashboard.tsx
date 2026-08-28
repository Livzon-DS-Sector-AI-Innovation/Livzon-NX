'use client'

import { fetchLkmsDashboard } from '@/lib/api/client/quality'

import { BaseTrendDashboard } from './TrendDashboardShared'

const LKMS_VET_ENTITY_CODE = 'qc_finished_lkms_vet'

interface LkmsTrendDashboardProps {
  entityCode?: string
}

export function LkmsTrendDashboard({ entityCode }: LkmsTrendDashboardProps) {
  const isSupportedEntity = entityCode === LKMS_VET_ENTITY_CODE

  return (
    <BaseTrendDashboard
      defaultTitle="林可霉素（兽药）趋势仪表盘"
      fetchDashboard={() => fetchLkmsDashboard(LKMS_VET_ENTITY_CODE)}
      entityCode={LKMS_VET_ENTITY_CODE}
      isSupportedEntity={isSupportedEntity}
      unsupportedMessage="目前仅 `林可霉素（兽药）` 子表会显示趋势仪表盘。"
      chartColumnSpan={6}
      descriptionText="当前仅对 `林可霉素（兽药）` 展示趋势仪表盘，按 3 图一行排布；`丙酮:≤2000ppm` 不展示标准上限线。"
    />
  )
}
