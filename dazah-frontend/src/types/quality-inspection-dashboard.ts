import type { components } from '@/types/generated/schema'

type S = components['schemas']

export type QualityInspectionDashboardSpecLine = S['InspectionDashboardSpecLine']
export type QualityInspectionDashboardPoint = S['InspectionDashboardPoint']
export type QualityInspectionDashboardChartSummary = S['InspectionDashboardChartSummary']
export type QualityInspectionDashboardChart = S['InspectionDashboardChart']
export type QualityInspectionDashboardAlert = S['InspectionDashboardAlert']
export type QualityInspectionDashboardSummary = S['InspectionDashboardSummary']
// generated schema 中 InspectionDashboardData 含 required `configured`（@default true），
// 但前端仅消费 meta.configured，且手写类型中 data 无该字段。
// 此处将 data.configured 放宽为 optional 以保持兼容（符合 OpenAPI 中 @default 的语义）。
export type QualityInspectionDashboardData = Omit<S['InspectionDashboardData'], 'configured'> & {
  configured?: boolean
}
export type QualityInspectionDashboardMeta = S['InspectionDashboardMeta']
// generated 的 InspectionDashboardResponse.data 引用的是原始 InspectionDashboardData（含 required configured），
// 这里用上面的兼容别名重建 ApiResponse，使 data.configured 保持 optional。
export type QualityInspectionDashboardApiResponse = Omit<
  S['InspectionDashboardResponse'],
  'data'
> & { data: QualityInspectionDashboardData }
