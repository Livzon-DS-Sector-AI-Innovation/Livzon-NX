/** 批号类型下拉选项 - MCTraceButton 和追溯页共用 */
const BATCH_TYPES = [
  { value: 'fermentation', label: '发酵液批号' },
  { value: 'refining', label: '提炼生产批号' },
  { value: 'na_batch', label: '钠化批号' },
  { value: 'crude_product', label: '粗品批号' },
  { value: 'extraction', label: '萃取批号' },
  { value: 'wet_powder', label: '一次精品批号' },
  { value: 'refinement', label: '二次结晶批号' },
  { value: 'single_batch_blend', label: '单批批号(混粉)' },
  { value: 'single_batch_qc', label: '单批批号(入库)' },
  { value: 'blending', label: '混合批号' },
  { value: 'front_batch', label: '前台批号' },
  { value: 'qc', label: '成品后台批号' },
]

export default BATCH_TYPES
