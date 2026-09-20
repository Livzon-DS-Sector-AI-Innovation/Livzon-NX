// 生产汇总表与产销计划卡共用的产线识别信息。
// 色相与顶部导航块一致；色相互不重叠，新增红/金避开既有紫蓝橙绿玫红青。
export const PRODUCT_COLORS: Record<string, string> = {
  MC: '#1677ff',
  DR: '#d46b08',
  FA: '#389e0d',
  LV: '#c41d7f',
  MV: '#08979c',
  TY: '#cf1322',
  FL: '#d4b106',
}

// 两卡共用的固定产线行序：生产汇总表与产销计划卡上下行对齐，
// 同一产品在两张表中处于同一行位置，便于竖向对照阅读。
export const PRODUCT_LINE_ORDER = [
  { code: 'MC', name: '霉酚酸' },
  { code: 'DR', name: '多拉菌素' },
  { code: 'FA', name: 'L-苯丙氨酸' },
  { code: 'LV', name: '洛伐他汀' },
  { code: 'MV', name: '美伐他汀' },
  { code: 'TY', name: 'L-色氨酸' },
  { code: 'FL', name: '2%氟苯尼考预混剂' },
] as const

// 销售计划明细只有 product_name，经此映射取产线色与行序
export const PRODUCT_NAME_TO_CODE: Record<string, string> = Object.fromEntries(
  PRODUCT_LINE_ORDER.map((line) => [line.name, line.code]),
)
