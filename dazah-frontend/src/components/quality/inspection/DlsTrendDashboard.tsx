'use client'

import { fetchDlsDashboard } from '@/lib/api/client/quality'

import { BaseTrendDashboard } from './TrendDashboardShared'

const DLS_GB_ENTITY_CODE = 'qc_finished_dor_gb'
const DLS_VET_ENTITY_CODE = 'qc_finished_dor_vet'

interface DlsTrendDashboardProps {
  entityCode?: string
}

export function DlsTrendDashboard({ entityCode }: DlsTrendDashboardProps) {
  const isSupportedEntity = entityCode === DLS_GB_ENTITY_CODE || entityCode === DLS_VET_ENTITY_CODE
  const activeEntityCode = entityCode === DLS_VET_ENTITY_CODE ? DLS_VET_ENTITY_CODE : DLS_GB_ENTITY_CODE

  return (
    <BaseTrendDashboard
      defaultTitle="多拉菌素趋势仪表盘"
      fetchDashboard={(code) => fetchDlsDashboard(code)}
      entityCode={activeEntityCode}
      isSupportedEntity={isSupportedEntity}
      unsupportedMessage="仅 `多拉菌素（GB）` 和 `多拉菌素（兽药）` 两个子表会显示趋势仪表盘。"
      chartColumnSpan={6}
      descriptionText="仪表盘仅跟随 `多拉菌素（GB）` / `多拉菌素（兽药）` 两个子表切换，通知对象固定为梁友辉、席晓。"
    />
  )
}
