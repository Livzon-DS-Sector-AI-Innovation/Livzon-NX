export const PRODUCTION_OVERVIEW_SECTIONS = [
  { key: 'MC', label: '霉酚酸' },
  { key: 'LN', label: '林可' },
  { key: 'DR', label: '多拉菌素' },
  { key: 'FA', label: 'L-苯丙氨酸' },
  { key: 'LV', label: '洛伐他汀' },
  { key: 'MV', label: '美伐他汀' },
  { key: 'TY', label: 'L-色氨酸' },
  { key: 'FL', label: '氟苯尼考' },
  { key: 'sales_plan', label: '产销计划' },
] as const

export const PRODUCTION_OVERVIEW_SECTION_KEYS = PRODUCTION_OVERVIEW_SECTIONS.map((item) => item.key)
export const PRODUCTION_OVERVIEW_PRODUCT_CODES: string[] = PRODUCTION_OVERVIEW_SECTION_KEYS.filter(
  (key) => key !== 'sales_plan',
)

export const PRODUCTION_SCHEDULING_SECTIONS = PRODUCTION_OVERVIEW_SECTIONS.filter(
  (item) => item.key !== 'FL' && item.key !== 'sales_plan',
)

export function productionPageSections(pageKey?: string) {
  if (pageKey === 'production:overview') return PRODUCTION_OVERVIEW_SECTIONS
  if (pageKey === 'production:plan:scheduling') return PRODUCTION_SCHEDULING_SECTIONS
  return []
}
