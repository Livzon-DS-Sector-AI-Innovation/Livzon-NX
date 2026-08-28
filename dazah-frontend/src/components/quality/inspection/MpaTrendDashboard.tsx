'use client'

import { fetchMpaDashboard } from '@/lib/api/client/quality'

import { BaseTrendDashboard } from './TrendDashboardShared'

const MPA_INTERNAL_ENTITY_CODE = 'qc_finished_internal'
const MPA_HIGH_SPEC_ENTITY_CODE = 'qc_finished_high_spec'

interface MpaTrendDashboardProps {
  entityCode?: string
}

export function MpaTrendDashboard({ entityCode }: MpaTrendDashboardProps) {
  const isSupportedEntity =
    entityCode === MPA_INTERNAL_ENTITY_CODE || entityCode === MPA_HIGH_SPEC_ENTITY_CODE
  const activeEntityCode =
    entityCode === MPA_HIGH_SPEC_ENTITY_CODE ? MPA_HIGH_SPEC_ENTITY_CODE : MPA_INTERNAL_ENTITY_CODE

  const descriptionText =
    activeEntityCode === MPA_HIGH_SPEC_ENTITY_CODE
      ? '当前展示 `霉酚酸（高规）` 子表的干燥失重、熔点、炽灼残渣、总杂质、最大单一杂质、含量、乙酸丁酯 7 项趋势，按 4 个一行布局。'
      : '当前展示 `霉酚酸（内控）` 子表的干燥失重、熔点、炽灼残渣、总杂质、单一最大杂质、含量、乙酸丁酯 7 项趋势，按 4 个一行布局。'

  return (
    <BaseTrendDashboard
      defaultTitle="霉酚酸趋势仪表盘"
      fetchDashboard={(code) => fetchMpaDashboard(code)}
      entityCode={activeEntityCode}
      isSupportedEntity={isSupportedEntity}
      unsupportedMessage="当前仅 `霉酚酸（内控）` 和 `霉酚酸（高规）` 两个子表显示趋势仪表盘。"
      descriptionText={descriptionText}
      defaultSourceLabel="霉酚酸（内控）"
    />
  )
}
