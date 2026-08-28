import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  mappings: [] as Array<Record<string, unknown>>,
  fetchTrainingDeptMappings: vi.fn(async () => mocks.mappings),
}))

vi.mock('@/lib/api/client/hr', () => ({
  fetchTrainingDeptMappings: mocks.fetchTrainingDeptMappings,
}))

import {
  buildKeyPathMap,
  buildMenuTree,
  collectAncestorKeys,
  filterActiveMenus,
  findSelectedKey,
  type MenuFlatItem,
} from './menu-tree'
import {
  getRegistrationCertificateSheetName,
  isRegistrationCertificateSheetKey,
} from './registration-certificate'
import { isRegistrationDeclarationProgressSheetKey } from './registration-declaration-progress'
import { isRegistrationProjectLedgerSheetKey } from './registration-project-ledger'
import { getLiquidInspectionGroupLabel, getSolidInspectionGroupLabel } from './quality-inspection-material-groups'
import { parseFeishuBaseUrl, parseFeishuBitableUrl } from './feishu-url'
import { formatQualityFeishuTestSummary, formatQualitySyncSummary } from './format/quality'
import { normalizeWarehouseDashboard } from './warehouse-dashboard'
import { resolveWarehousePageQueryParams } from './warehouse-page-query'
import { isRawScopePageKey, warehouseScopeOf, warehouseScopeWritePermission } from '@/components/warehouse/warehouseScope'
import {
  getCandidateSourceMap,
  getModalRules,
  refreshDeptMappings,
  resolveTrainingDept,
  unifyDept,
  withSubDepts,
} from '@/components/hr/trainingDept'
import {
  buildTrendOption,
  buildXAxisLabelFormatter,
  formatMetricValue,
  formatSpecLines,
  getNotificationTag,
} from '@/components/quality/inspection/TrendDashboardShared'
import {
  cnToInt as annualCnToInt,
  extractAnnexRefs as extractAnnualAnnexRefs,
  toHalfDigits,
} from '@/components/hr/AnnualPlanDetailClient'
import {
  extractAnnexRefs as extractTrainingAnnexRefs,
  formatTopicForSignin,
  matchDrugCategory,
  matchTrainingType,
} from '@/components/hr/TrainingSignInTabsClient'
import {
  buildCompanyCountryDisplay,
  buildLedgerGroupKey,
  buildLedgerMainCreatePayload,
  buildLedgerMainUpdatePayload,
  buildLedgerUpdateCreatePayload,
  buildLedgerUpdatePatchPayload,
  buildSelectOptions,
  displayText,
  getLedgerDateSortValue,
  normalizeLedgerRecord,
  normalizeNullableText,
  normalizeRequiredText,
  removeLedgerUpdateRecord,
  replaceLedgerMainRecord,
  sortLedgerRecords,
  sortLedgerUpdates,
  upsertLedgerUpdateRecord,
} from '@/components/registration/AuthorizationLetterClient'
import {
  buildHistoryColumns,
  buildHistoryDisplayRecords,
  getColumnWidth,
  getMainCellClampLines,
  isColumnHidden,
  isMultilineField,
  renderCellValue,
  toEntryInput,
} from '@/components/registration/ProjectLedgerSheetPage'
import {
  buildQueryParams,
  formatDate as formatTrackerDate,
  hasCompletedAnalysis,
  renderMultilineText,
} from '@/components/registration/RegulationTrackerPage'
import dayjs from 'dayjs'
import {
  buildAdvancedFilterLabel,
  buildDateFilterLabel,
  buildGroupedRows,
  buildVisiblePageData,
  formatDateValue,
  formatDetailDisplayValue,
  getUniqueOptions,
  isDateLikeColumn,
  parseAdvancedFilters,
  resolveDateFilterRange,
  resolveInoutLinks,
  resolveWeekRange,
} from '@/components/warehouse/WarehouseFeishuTablePage'

function menu(id: string, parent_id: string | null, sort_order: number, status = 'active'): MenuFlatItem {
  return {
    id,
    key: id,
    parent_id,
    name: id,
    type: 'menu',
    permission_code: null,
    route_path: `/${id}`,
    component_path: null,
    icon: null,
    sort_order,
    status,
  }
}

describe('migrated pure helper contracts', () => {
  it('builds, filters and selects the database-driven menu tree', () => {
    const items = [
      menu('child', 'parent', 1),
      menu('parent', null, 2),
      menu('orphan', 'missing', 0),
      menu('disabled', null, 3, 'disabled'),
      menu('disabled-child', 'disabled', 1),
    ]
    items[0].route_path = '/parent/child'
    const tree = buildMenuTree(items)
    expect(tree.map((node) => node.id)).toEqual(['orphan', 'parent', 'disabled'])
    expect(tree[1].children.map((node) => node.id)).toEqual(['child'])
    expect(filterActiveMenus(items).map((item) => item.id)).toEqual(['child', 'parent', 'orphan'])
    expect(findSelectedKey(tree, '/parent/child/detail')).toBe('child')
    expect(collectAncestorKeys(tree, '/parent/child/detail')).toEqual(['parent', 'child'])
    expect(buildKeyPathMap(tree).get('child')).toBe('/parent/child')
  })

  it('normalizes warehouse dashboards and query parameters without throwing on partial data', async () => {
    expect(normalizeWarehouseDashboard('raw', { safety: { total: '3', ok: 2 }, quality: null })).toMatchObject({
      safety: { total: 3, ok: 2, low: 0 },
      quality: { 合格: 0, 待验: 0, 不合格: 0 },
    })
    expect(normalizeWarehouseDashboard('hardware', { stock_amount: '10', dept_stock: 'bad' })).toMatchObject({
      stock_amount: 10,
      dept_stock: [],
    })
    expect(normalizeWarehouseDashboard('product', { qualified: 4, product_stock: [{ name: 'A' }] })).toMatchObject({
      qualified: 4,
      product_stock: [{ name: 'A' }],
      product_outbound: [],
    })

    const query = await resolveWarehousePageQueryParams(Promise.resolve({
      page: ['2', '3'],
      page_size: '50',
      keyword: '物料',
      filters: JSON.stringify([{ field: '名称', operator: 'contains', value: '酸' }]),
    }))
    expect(query).toMatchObject({ page: 2, page_size: 50, keyword: '物料' })
    expect(query.filters).toHaveLength(1)
    await expect(resolveWarehousePageQueryParams(Promise.resolve({ filters: '{bad' }))).resolves.toMatchObject({
      filters: undefined,
    })
  })

  it('keeps registration, quality, Feishu URL and warehouse scope mappings explicit', () => {
    expect(isRegistrationCertificateSheetKey('domestic-gmp')).toBe(true)
    expect(isRegistrationCertificateSheetKey('unknown')).toBe(false)
    expect(getRegistrationCertificateSheetName('domestic-gmp')).toBe('国内GMP')
    expect(isRegistrationDeclarationProgressSheetKey('gmp-projects')).toBe(true)
    expect(isRegistrationDeclarationProgressSheetKey('unknown')).toBe(false)
    expect(isRegistrationProjectLedgerSheetKey('domestic-standalone-review')).toBe(true)
    expect(getSolidInspectionGroupLabel('ys-100')).toBe('YS100')
    expect(getLiquidInspectionGroupLabel('yl-2xx')).toBe('YL2xx')
    expect(parseFeishuBitableUrl('https://example.feishu.cn/base/app-token?table=tbl-1')).toEqual({
      app_token: 'app-token',
      table_id: 'tbl-1',
    })
    expect(parseFeishuBitableUrl('not-a-url')).toBeNull()
    expect(parseFeishuBaseUrl('https://example.feishu.cn/base/app-token')).toBe('app-token')
    expect(parseFeishuBaseUrl('https://example.com/no-base')).toBeNull()
    expect(formatQualitySyncSummary({ entity_label: 'CAPA', synced: 2, failed: 1, conflicts: 3 })).toContain('CAPA回拉完成')
    expect(formatQualityFeishuTestSummary({ success: false, message: '无权限' })).toBe('连接失败：无权限')
    expect(warehouseScopeOf('product-detail')).toBe('product')
    expect(warehouseScopeOf('hardware-summary')).toBe('hardware')
    expect(warehouseScopeWritePermission('raw')).toBe('warehouse:raw:write')
    expect(isRawScopePageKey('packaging-summary')).toBe(true)
  })

  it('applies HR training mappings and inspection trend formatting rules', async () => {
    mocks.mappings = [
      { mapping_type: 'special', source_name: '二车间', target_name: '培训二车间', match_level: 'second', priority: 1 },
      { mapping_type: 'print_unify', source_name: '二车间（MC）', target_name: '二车间', match_level: 'both', priority: 1 },
      { mapping_type: 'exclude', source_name: '临时部门', target_name: null, match_level: 'first', priority: 1 },
      { mapping_type: 'force_show', source_name: '培训中心', target_name: null, match_level: 'first', priority: 1 },
      { mapping_type: 'candidate_source', source_name: '源部门', target_name: '培训部门', match_level: 'first', priority: 1 },
      { mapping_type: 'modal_drop', source_name: '不参与', target_name: null, match_level: 'first', priority: 1 },
      { mapping_type: 'modal_extra', source_name: '额外行', target_name: null, match_level: 'first', priority: 1 },
      { mapping_type: 'modal_no_expand', source_name: '不展开', target_name: null, match_level: 'first', priority: 1 },
    ]
    await refreshDeptMappings()
    expect(resolveTrainingDept('一级', '二车间', [])).toBe('培训二车间')
    expect(resolveTrainingDept('质量部', undefined, ['质量部'])).toBe('质量部')
    expect(resolveTrainingDept('未知', '二级', [])).toBe('二级')
    expect(unifyDept('二车间（MC）')).toBe('二车间')
    expect(withSubDepts(['临时部门', '质量部'])).toEqual(['培训中心', '质量部'])
    expect(getCandidateSourceMap()).toEqual({ 源部门: '培训部门' })
    const rules = getModalRules()
    expect(rules.drop.has('不参与')).toBe(true)
    expect(rules.extra).toEqual(['额外行'])
    expect(rules.noExpand.has('不展开')).toBe(true)

    expect(formatMetricValue(null)).toBe('-')
    expect(formatMetricValue(1.2)).toBe('1.2')
    expect(formatSpecLines([{ label: '上限', value: 2 }, { label: '下限', value: 0 }])).toBe('上限 2 / 下限 0')
    const formatter = buildXAxisLabelFormatter(['A', 'B'], false)
    expect(formatter('', 1)).toBe('B')
    const longFormatter = buildXAxisLabelFormatter(Array.from({ length: 30 }, (_, index) => String(index)), false)
    expect(longFormatter('', 0)).toBe('0')
    expect(longFormatter('', 1)).toBe('')
    const tag = getNotificationTag({ notification_deduplicated: false, notification_status: 'partial' } as never)
    expect(tag.props.color).toBe('gold')
    const option = buildTrendOption({
      metric_label: '含量',
      categories: ['A', 'B'],
      actual_series: [1, 2],
      mean_series: [1, 1],
      upper_sigma_series: [2, 2],
      lower_sigma_series: [0, 0],
      spec_lines: [{ label: '标准上限', value: 3 }],
    } as never, false)
    expect(option.series).toHaveLength(5)
  })

  it('covers migrated HR, registration and warehouse transformation helpers', () => {
    expect(annualCnToInt('')).toBeNull()
    expect(annualCnToInt('12')).toBe(12)
    expect(annualCnToInt('十')).toBe(10)
    expect(annualCnToInt('二十一')).toBe(21)
    expect(toHalfDigits('２０２６')).toBe('2026')
    expect(extractAnnualAnnexRefs('附件１、附件二、附件二、附件十一')).toEqual(['附件1', '附件2', '附件11'])

    expect(matchTrainingType('GMP培训', '')).toBe('质量培训')
    expect(matchTrainingType('内部文件', 'SOP-PM-106/03')).toBe('管理类')
    expect(matchTrainingType('未知主题', '')).toBeUndefined()
    expect(matchDrugCategory('兽药质量', '')).toBe('兽药')
    expect(matchDrugCategory('GMP基础', '')).toBe('人药')
    expect(matchDrugCategory('普通培训', '')).toBeUndefined()
    expect(formatTopicForSignin([{ name: 'SOP', code: 'SOP-1' }])).toBe('《SOP》（SOP-1）')
    expect(formatTopicForSignin([{ name: '一' }, { name: '二', resolvedCode: 'S-2' }, { name: '三' }])).toContain('等3份')
    expect(extractTrainingAnnexRefs('附件一、附件２、附件二')).toEqual(['附件1', '附件2'])

    expect(normalizeNullableText('  ')).toBeNull()
    expect(normalizeNullableText(' x ')).toBe('x')
    expect(normalizeRequiredText(' x ')).toBe('x')
    expect(displayText('')).toBe('-')
    expect(buildSelectOptions(['A', 'A', null, 'B'])).toEqual([{ label: 'A', value: 'A' }, { label: 'B', value: 'B' }])
    expect(getLedgerDateSortValue('')).toBe(Number.MAX_SAFE_INTEGER)
    expect(getLedgerDateSortValue('bad')).toBe(Number.MAX_SAFE_INTEGER)
    expect(getLedgerDateSortValue('2026/2/3')).toBe(20260203)
    const updateA = { id: 'b', sort_order: 1 } as never
    const updateB = { id: 'a', sort_order: 1 } as never
    expect(sortLedgerUpdates([updateA, updateB]).map((item) => item.id)).toEqual(['a', 'b'])
    const mainA = { id: 'a', product_name: 'B', market_name: '', updates: [updateA] }
    const mainB = { id: 'b', product_name: 'A', market_name: '', updates: [] }
    expect(buildLedgerGroupKey(mainA as never)).toContain('B||')
    expect(normalizeLedgerRecord(mainA as never).updates).toHaveLength(1)
    expect(sortLedgerRecords([mainA, mainB] as never).map((item) => item.id)).toEqual(['b', 'a'])
    expect(replaceLedgerMainRecord([mainA] as never, { ...mainA, product_name: 'C' } as never)[0].product_name).toBe('C')
    expect(upsertLedgerUpdateRecord([mainA] as never, 'a', { id: 'c', sort_order: 2 } as never)[0].updates).toHaveLength(2)
    expect(upsertLedgerUpdateRecord([mainA] as never, 'a', { id: 'b', sort_order: 2 } as never)[0].updates[0].id).toBe('b')
    expect(removeLedgerUpdateRecord([mainA] as never, 'a', 'b')[0].updates).toHaveLength(0)
    const entryValues = { product_name: ' 产品 ', authorization_file_name: ' 文件 ', status: '' } as never
    expect(buildLedgerMainCreatePayload(entryValues)).toMatchObject({ product_name: '产品', authorization_file_name: '文件', status: '待确认' })
    expect(buildLedgerMainUpdatePayload(entryValues)).toMatchObject({ product_name: '产品', status: '待确认' })
    expect(buildLedgerUpdateCreatePayload({ authorization_date: ' 2026-01-01 ', handler: '', remarks: undefined })).toEqual({ authorization_date: '2026-01-01', handler: null, remarks: null })
    expect(buildLedgerUpdatePatchPayload({ authorization_date: '', handler: '张三', remarks: '备注' })).toEqual({ authorization_date: null, handler: '张三', remarks: '备注' })
    expect(buildCompanyCountryDisplay({ company_name: '公司', country: '中国' } as never)).toBe('公司\n中国')
    expect(buildCompanyCountryDisplay({ company_name: '', country: '' } as never)).toBe('-')

    expect(renderCellValue(null)).toBe('—')
    expect(renderCellValue('内容', { compact: true, clampLines: 2 })).toBeTruthy()
    const labels = ['序号', '产品', '项目名称', '质量标准', '批量/包装规格', '程序类型1', 'RMS/CMS个数', '是否获得证书', '药政活动类型', '交费/时间', '文件递交日期', '递交时间', '签署日期', '官方登记号', '登记号', '证书效期', '证书名称', '内部编号', '国家/受理机构', '代理机构', '药物类型', '制剂剂型/规格/官方登记号', 'MF官方登记号', '审评结果', '备注', '其他']
    expect(labels.map(getColumnWidth)).toEqual(expect.arrayContaining([64, 108, 132, 154]))
    expect(getMainCellClampLines('项目名称')).toBe(2)
    expect(getMainCellClampLines('药物类型')).toBe(2)
    expect(getMainCellClampLines('其他')).toBe(1)
    expect(isMultilineField('药政活动说明')).toBe(true)
    expect(isMultilineField('名称')).toBe(false)
    expect(isColumnHidden('unknown', '名称')).toBe(false)
    expect(isColumnHidden('international-standalone-review', '证书编号')).toBe(true)
    const projectColumns = [{ key: 'project_name', label: '项目名称' }, { key: 'remarks', label: '备注' }] as never
    const history = buildHistoryDisplayRecords([{ id: 'h1', version: 1, values: { project_name: '项目A' } }] as never, projectColumns)
    expect(history[0].displayValues).toEqual({ project_name: '项目A', remarks: null })
    expect(buildHistoryColumns(projectColumns, 1)).toHaveLength(3)
    expect(toEntryInput('projects', projectColumns, { project_name: ' A ', remarks: '' })).toEqual({ sheet_key: 'projects', values: { project_name: 'A', remarks: null } })

    expect(formatTrackerDate()).toBe('-')
    expect(formatTrackerDate('invalid')).toBe('invalid')
    expect(formatTrackerDate('2026-08-25T09:00:00Z', true)).toMatch(/^2026-08-25/)
    expect(renderMultilineText()).toBe('-')
    expect(renderMultilineText('长文本', 2)).toBeTruthy()
    expect(hasCompletedAnalysis()).toBe(false)
    expect(hasCompletedAnalysis({ ai_analysis_status: 'completed', ai_summary: null })).toBe(true)
    expect(hasCompletedAnalysis({ ai_analysis_status: 'pending', ai_summary: ' 已有摘要 ' })).toBe(true)
    expect(buildQueryParams({ keyword: '  关键字 ', sourceSite: 'NMPA', publishDateRange: [dayjs('2026-08-01'), dayjs('2026-08-02')], captureDateRange: [dayjs('2026-08-03'), null], isNew: false })).toMatchObject({ keyword: '关键字', sourceSite: 'NMPA', publishDateFrom: '2026-08-01', publishDateTo: '2026-08-02', captureDateFrom: '2026-08-03', isNew: false })

    expect(resolveInoutLinks('raw-ledger')).toMatchObject({ inbound: expect.any(String), outbound: expect.any(String) })
    expect(resolveInoutLinks('unknown')).toBeNull()
    expect(isDateLikeColumn('入库日期')).toBe(true)
    expect(isDateLikeColumn('名称')).toBe(false)
    expect(formatDateValue(null)).toBeNull()
    expect(formatDateValue(0)).toBe('1970-01-01')
    expect(formatDateValue(1_700_000_000_000)).toMatch(/^2023-/)
    expect(formatDateValue('1700000000')).toMatch(/^2023-/)
    expect(formatDateValue('普通文本')).toBe('普通文本')
    const week = resolveWeekRange(dayjs('2026-08-26'))
    expect(week.start.format('YYYY-MM-DD')).toBe('2026-08-24')
    expect(resolveDateFilterRange('eq', dayjs('2026-08-01'))).toEqual({ startDate: '2026-08-01', endDate: '2026-08-01' })
    expect(resolveDateFilterRange('gt', dayjs('2026-08-01'))).toEqual({ startDate: '2026-08-01', endDate: '' })
    expect(resolveDateFilterRange('lt', dayjs('2026-08-01'))).toEqual({ startDate: '', endDate: '2026-08-01' })
    expect(resolveDateFilterRange('this_week', null).startDate).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(buildDateFilterLabel('', '', '')).toBe('')
    expect(buildDateFilterLabel('eq', '2026-08-01', '')).toContain('等于')
    expect(buildDateFilterLabel('between', '', '')).toContain('between')
    expect(parseAdvancedFilters(null)).toEqual([])
    expect(parseAdvancedFilters('{bad')).toEqual([])
    expect(parseAdvancedFilters(JSON.stringify([{ field: '名称', operator: 'contains', value: '酸' }]))).toHaveLength(1)
    const warehouseRows = [{ 产品: 'A', 预警: '', 数量: 2 }, { 产品: 'B', 预警: '不足', 数量: 1 }] as never
    expect(getUniqueOptions(warehouseRows, ['产品', '缺失'])).toHaveLength(2)
    expect(buildAdvancedFilterLabel({ field: '名称', operator: 'empty', value: '' } as never)).toContain('为空')
    expect(buildAdvancedFilterLabel({ field: '数量', operator: 'between', value: '1', value_to: '3' } as never)).toContain('~')
    expect(formatDetailDisplayValue({ field_name: '备注', value: [{ name: '张三' }, '文本', null] } as never)).toBe('张三、文本、null')
    expect(formatDetailDisplayValue({ field_name: '启用', value: true } as never)).toBe('是')
    expect(buildGroupedRows([{ 产品: 'B' }, { 产品: 'A' }, { 产品: '' }] as never, ['产品']).filter((row) => '__group_row' in row)).toHaveLength(3)
    expect(buildGroupedRows([{ name: 'A' }] as never, [])).toEqual([{ name: 'A' }])
    const visible = buildVisiblePageData('raw-summary', { columns: [{ key: '物料名称', title: '物料名称', field_type: 1 }], rows: [{ 物料名称: '物料A' }], page_key: 'raw-summary' } as never)
    expect(visible.columns).toHaveLength(1)
    expect(buildVisiblePageData('unknown', { columns: [{ key: '父记录', title: '父记录' }, { key: '有效期', title: '有效期' }], rows: [{ 父记录: 'x', 有效期: 1700000000 }], page_key: 'unknown' } as never).columns).toHaveLength(1)
  })
})
