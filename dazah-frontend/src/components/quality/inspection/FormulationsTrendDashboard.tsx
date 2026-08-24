'use client'

import { fetchFormulationsDashboard } from '@/lib/api/client/quality'

import { BaseTrendDashboard } from './TrendDashboardShared'

const FLU_ENTITY_CODE = 'qc_finished_flu_powder'
const FEN_ENTITY_CODE = 'qc_finished_fen_powder'

interface FormulationsTrendDashboardProps {
  entityCode?: string
}

export function FormulationsTrendDashboard({ entityCode }: FormulationsTrendDashboardProps) {
  const isSupportedEntity = entityCode === FLU_ENTITY_CODE || entityCode === FEN_ENTITY_CODE
  const activeEntityCode = entityCode === FEN_ENTITY_CODE ? FEN_ENTITY_CODE : FLU_ENTITY_CODE

  return (
    <BaseTrendDashboard
      defaultTitle="预混剂趋势仪表盘"
      fetchDashboard={(code) => fetchFormulationsDashboard(code)}
      entityCode={activeEntityCode}
      isSupportedEntity={isSupportedEntity}
      unsupportedMessage="仅 `2%氟苯尼考预混剂` 和 `5%芬苯达唑粉` 两个子表会显示趋势仪表盘。"
      chartColumnSpan={12}
      descriptionText="仪表盘跟随 `2%氟苯尼考预混剂` / `5%芬苯达唑粉` 两个子表切换，当前分别展示干燥失重和含量测定两项趋势。"
    />
  )
}
