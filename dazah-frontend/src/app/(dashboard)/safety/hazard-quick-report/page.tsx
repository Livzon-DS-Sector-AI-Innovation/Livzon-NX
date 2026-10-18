import {
  getSafetyPageTableRecords,
  getSafetyPageTableStats,
  getSafetyPageTableTabs,
} from '@/actions/safety'
import { PageFeishuTable } from '@/components/safety'
import {
  SAFETY_PAGE_TABLE_KEYS,
  toPageTableStats,
  toPageTableTabs,
  toRecordRows,
} from '@/lib/safety-page-tables'

export const dynamic = 'force-dynamic'

const PAGE_NAME = '隐患台账'

// 公司总台账 Base 有多张子表（2024-2026 公司级检查、上级部门检查、事业
// 部检查、不符合项、观察项）。「检查内容」才是检查日期（schema 里排在前的
// 是「目标完成日期」），因此显式指定统计分组；仪表盘跟随所选数据表与筛
// 选条件联动。负责人分布面向台账追责视角，关闭状态即整改情况。
const STATS_GROUP_BY = ['检查内容', '部门/车间', '负责人', '关闭状态']
// 明细默认按「部门/车间」归组排序（无该字段的子表自动回退默认顺序）
const DEFAULT_SORT_FIELD = '部门/车间'
// 筛选栏：部门/负责人/状态下拉 + 检查内容时间范围
const FILTER_FIELDS = ['部门/车间', '负责人', '关闭状态']
const FILTER_DATE_FIELD = '检查内容'
// 到期提醒：按目标完成日期统计未关闭临期/逾期（仪表盘卡片 + 每日推送同口径）
const DUE_FIELD = '目标完成日期'

export default async function SafetyHazardQuickReportPage() {
  const pageKey = SAFETY_PAGE_TABLE_KEYS.hazardQuickReport
  // 先取子表清单确定主表，首屏仪表盘与客户端默认选中（主表）口径一致
  const tabsRes = await getSafetyPageTableTabs({ pageKey })
  const tabs = toPageTableTabs(tabsRes.code === 200 ? tabsRes.data?.tabs : null)
  const primaryTableId = tabs.find((tab) => tab.is_primary)?.table_id ?? null
  const [res, statsRes] = await Promise.all([
    getSafetyPageTableRecords({
      pageKey,
      page: 1,
      pageSize: 20,
      sortField: DEFAULT_SORT_FIELD,
    }),
    getSafetyPageTableStats({
      pageKey,
      groupBy: STATS_GROUP_BY,
      tableId: primaryTableId,
      dueField: DUE_FIELD,
      closeField: '关闭状态',
    }),
  ])
  const data = res.code === 200 && res.data ? res.data : null

  return (
    <div style={{ padding: '0 0 24px' }}>
      <h2 style={{ marginBottom: 16 }}>{PAGE_NAME}</h2>
      <PageFeishuTable
        pageKey={pageKey}
        pageName={PAGE_NAME}
        defaultSortField={DEFAULT_SORT_FIELD}
        filterFields={FILTER_FIELDS}
        filterDateField={FILTER_DATE_FIELD}
        dueField={DUE_FIELD}
        allowCreate
        initialData={
          data
            ? {
                columns: data.columns ?? [],
                records: toRecordRows(data.records),
                total: data.total,
                page: data.page,
                page_size: data.page_size,
                truncated: data.truncated,
              }
            : null
        }
        initialStats={statsRes.code === 200 ? toPageTableStats(statsRes.data) : null}
        initialError={data ? null : res.message || '读取多维表格数据失败'}
        statsGroupBy={STATS_GROUP_BY}
        tabs={tabs.length > 1 ? tabs : undefined}
      />
    </div>
  )
}
