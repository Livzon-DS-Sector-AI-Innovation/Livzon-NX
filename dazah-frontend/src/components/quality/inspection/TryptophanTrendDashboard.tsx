'use client'

import { fetchTryptophanDashboard } from '@/lib/api/client/quality'

import { BaseTrendDashboard } from './TrendDashboardShared'

const TRP_POWDER_ENTITY_CODE = 'qc_finished_trp_powder'
const TRP_GRANULE_ENTITY_CODE = 'qc_finished_trp_granule'

interface TryptophanTrendDashboardProps {
  entityCode?: string
}

export function TryptophanTrendDashboard({ entityCode }: TryptophanTrendDashboardProps) {
  const isSupportedEntity =
    entityCode === TRP_POWDER_ENTITY_CODE || entityCode === TRP_GRANULE_ENTITY_CODE
  const activeEntityCode =
    entityCode === TRP_POWDER_ENTITY_CODE ? TRP_POWDER_ENTITY_CODE : TRP_GRANULE_ENTITY_CODE

  const descriptionText =
    activeEntityCode === TRP_POWDER_ENTITY_CODE
      ? '当前展示 `色氨酸粉末` 子表的含量、比旋度、干燥失重、粗灰分、pH 5 项趋势，按 1 行 5 图布局。'
      : '当前展示 `色氨酸颗粒` 子表的含量、干燥失重、粗灰分、pH 4 项趋势，按 1 行 4 图布局。'

  return (
    <BaseTrendDashboard
      defaultTitle="色氨酸趋势仪表盘"
      fetchDashboard={(code) => fetchTryptophanDashboard(code)}
      entityCode={activeEntityCode}
      isSupportedEntity={isSupportedEntity}
      unsupportedMessage="当前仅 `色氨酸粉末` 和 `色氨酸颗粒` 两个子表显示趋势仪表盘。"
      chartCountPerRow={activeEntityCode === TRP_POWDER_ENTITY_CODE ? 5 : 4}
      descriptionText={descriptionText}
    />
  )
}
