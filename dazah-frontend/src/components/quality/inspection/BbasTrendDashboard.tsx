'use client'

import { fetchBbasDashboard } from '@/lib/api/client/quality'

import { BaseTrendDashboard } from './TrendDashboardShared'

const BBAS_FCC14_ENTITY_CODE = 'qc_finished_fcc14'
const BBAS_HANGUANG_K1_ENTITY_CODE = 'qc_finished_bbas_hanguang_k1'

interface BbasTrendDashboardProps {
  entityCode?: string
}

export function BbasTrendDashboard({ entityCode }: BbasTrendDashboardProps) {
  const isSupportedEntity =
    entityCode === BBAS_FCC14_ENTITY_CODE || entityCode === BBAS_HANGUANG_K1_ENTITY_CODE
  const activeEntityCode =
    entityCode === BBAS_HANGUANG_K1_ENTITY_CODE ? BBAS_HANGUANG_K1_ENTITY_CODE : BBAS_FCC14_ENTITY_CODE

  const descriptionText =
    activeEntityCode === BBAS_HANGUANG_K1_ENTITY_CODE
      ? '当前展示 `汉光（K1）` 子表的含量、比旋度、pH、透光率 4 项趋势，按 1 行 4 图布局。'
      : '当前展示 `FCC14` 子表的酸度（pH）、比旋度、含量（干燥品计）3 项趋势，按 1 行 3 图布局。'

  return (
    <BaseTrendDashboard
      defaultTitle="L-苯丙氨酸趋势仪表盘"
      fetchDashboard={(code) => fetchBbasDashboard(code)}
      entityCode={activeEntityCode}
      isSupportedEntity={isSupportedEntity}
      unsupportedMessage="当前仅 `FCC14` 和 `汉光（K1）` 两个子表显示趋势仪表盘。"
      chartColumnSpan={activeEntityCode === BBAS_HANGUANG_K1_ENTITY_CODE ? 6 : 8}
      descriptionText={descriptionText}
    />
  )
}
