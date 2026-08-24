'use client'

import { fetchWaterDashboard } from '@/lib/api/client/quality'

import { BaseTrendDashboard } from './TrendDashboardShared'

const PURE_WATER_ENTITY_CODE = 'qc_finished_pure_water'

interface WaterTrendDashboardProps {
  entityCode?: string
}

export function WaterTrendDashboard({ entityCode }: WaterTrendDashboardProps) {
  const isSupportedEntity = entityCode === PURE_WATER_ENTITY_CODE

  return (
    <BaseTrendDashboard
      defaultTitle="纯化水趋势仪表盘"
      fetchDashboard={() => fetchWaterDashboard(PURE_WATER_ENTITY_CODE)}
      entityCode={PURE_WATER_ENTITY_CODE}
      isSupportedEntity={isSupportedEntity}
      unsupportedMessage="当前仅 `纯化水` 子表显示趋势仪表盘。"
      chartCountPerRow={4}
      descriptionText="当前展示 `纯化水` 子表的电导率、TOC、不挥发物、微生物限度 4 项趋势，按 1 行 4 图布局。"
    />
  )
}
