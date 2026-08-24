'use client'

import { fetchMvtDashboard } from '@/lib/api/client/quality'

import { BaseTrendDashboard } from './TrendDashboardShared'

export function MvtTrendDashboard() {
  return (
    <BaseTrendDashboard
      defaultTitle="美伐他汀（DMF）趋势仪表盘"
      fetchDashboard={() => fetchMvtDashboard()}
      chartColumnSpan={8}
      descriptionText="仪表盘固定读取 `qc_finished_mvt`，仅展示美伐他汀（DMF）趋势。"
    />
  )
}
