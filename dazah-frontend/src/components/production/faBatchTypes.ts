/** FA 批号类型下拉选项 - FATraceButton 和追溯页共用 */
const FA_BATCH_TYPES = [
  { value: 'fermentation', label: '发酵液放罐' },
  { value: 'acidification', label: '酸化过滤' },
  { value: 'decolor1', label: '一次脱色过滤' },
  { value: 'decolor_centrifuge', label: '脱色离心' },
]

export default FA_BATCH_TYPES

export const FA_STAGE_CFG: Record<string, { color: string }> = {
  fermentation: { color: '#52c41a' },
  acidification: { color: '#1890ff' },
  decolor1: { color: '#13c2c2' },
  decolor_centrifuge: { color: '#722ed1' },
}

export const FA_STAGE_ORDER = ['fermentation', 'acidification', 'decolor1', 'decolor_centrifuge']
