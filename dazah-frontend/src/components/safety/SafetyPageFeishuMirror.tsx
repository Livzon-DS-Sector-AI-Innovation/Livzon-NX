import { getSafetyPageTableRecords } from '@/actions/safety'
import {
  SAFETY_PAGE_TABLE_DEFAULT_TODAY,
  SAFETY_PAGE_TABLE_KEYS,
  pickDefaultDateColumn,
  toRecordRows,
} from '@/lib/safety-page-tables'
import { PageFeishuTable } from '@/components/safety'

/**
 * 安全模块「页面 ↔ 飞书多维表格」镜像页的服务端壳层（仅作业安全栏目使用）。
 *
 * 服务端首屏拉取记录注入通用表格组件，列结构来自飞书实时表结构并按
 * 绑定的视图（view_id）裁剪对齐；表格绑定在「安全管理 → 系统配置 →
 * 飞书设置 → 页面数据表映射」中按页面配置，不写死在代码里。
 * 镜像页不启用统计仪表盘，表格只显示主要列；日报/巡查类页面默认按
 * 日期列筛选当天（报备表等小表默认显示全部），完整字段与多条件筛选
 * 在页面内交互查看。
 */
export default async function SafetyPageFeishuMirror({
  pageKey,
  pageName,
  preferredColumnNames,
  createUrl,
}: {
  pageKey: (typeof SAFETY_PAGE_TABLE_KEYS)[keyof typeof SAFETY_PAGE_TABLE_KEYS]
  pageName: string
  /** 表格优先展示的关键列（可选）；不传保持自动摘要。 */
  preferredColumnNames?: readonly string[]
  /** 「新增」按钮的跳转链接（可选，如飞书审批填单页）；不传不显示新增按钮。 */
  createUrl?: string
}) {
  const first = await getSafetyPageTableRecords({
    pageKey,
    page: 1,
    pageSize: 20,
  })
  let data = first.code === 200 && first.data ? first.data : null

  // 日报/巡查类页面默认当天：先取列结构确定日期列，再按当天过滤取首屏。
  // “当天”按工厂所在地时区计算，避免服务器 UTC 时区跨日偏差。
  const wantToday = SAFETY_PAGE_TABLE_DEFAULT_TODAY.has(pageKey)
  const dateColumn =
    data && wantToday ? pickDefaultDateColumn(data.columns ?? []) : null
  let initialDateFilter: { field: string; value: string } | null = null
  if (data && dateColumn) {
    const today = new Date().toLocaleDateString('sv-SE', {
      timeZone: 'Asia/Shanghai',
    })
    initialDateFilter = { field: dateColumn.name, value: today }
    const filtered = await getSafetyPageTableRecords({
      pageKey,
      page: 1,
      pageSize: 20,
      conditions: [initialDateFilter],
    })
    if (filtered.code === 200 && filtered.data) {
      data = filtered.data
    }
  }

  return (
    <div style={{ padding: '0 0 24px' }}>
      <h2 style={{ marginBottom: 16 }}>{pageName}</h2>
      <PageFeishuTable
        pageKey={pageKey}
        pageName={pageName}
        showStats={false}
        summarizeColumns
        preferredColumnNames={preferredColumnNames}
        createUrl={createUrl}
        initialDateFilter={initialDateFilter}
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
        initialError={data ? null : first.message || '读取多维表格数据失败'}
      />
    </div>
  )
}
