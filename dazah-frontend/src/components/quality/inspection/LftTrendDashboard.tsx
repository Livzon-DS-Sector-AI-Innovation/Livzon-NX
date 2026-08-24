'use client'

import { fetchLftDashboard } from '@/lib/api/client/quality'

import { BaseTrendDashboard } from './TrendDashboardShared'

const LFT_EP_ENTITY_CODE = 'qc_finished_lft_ep'
const LFT_USP_ENTITY_CODE = 'qc_finished_lft_usp'

interface LftTrendDashboardProps {
  entityCode?: string
}

export function LftTrendDashboard({ entityCode }: LftTrendDashboardProps) {
  const activeEntityCode = entityCode === LFT_USP_ENTITY_CODE ? LFT_USP_ENTITY_CODE : LFT_EP_ENTITY_CODE

  return (
    <BaseTrendDashboard
      defaultTitle="洛伐他汀趋势仪表盘"
      fetchDashboard={(code) => fetchLftDashboard(code)}
      entityCode={activeEntityCode}
      chartColumnSpan={6}
      descriptionText="仪表盘仅跟随 `洛伐他汀（EP）` / `洛伐他汀（USP）` 两个子表切换，通知对象固定为罗勇、周方圆。"
    />
  )
}
