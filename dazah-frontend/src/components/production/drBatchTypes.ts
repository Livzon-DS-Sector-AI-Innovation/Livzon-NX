/**
 * DR 多拉菌素追溯下拉选项
 *
 * - DR_BATCH_TYPES：按工段类型（7 工段），供完整追溯页等自由选择起点的场景使用。
 * - FIELD_OPTIONS_BY_MODULE：按工段页（initialModule）映射该页台账表实际批号字段。
 *   追溯按钮下拉按当前工段页只显示对应字段，避免与表内列名对不上。
 *   value 为后端 /dr/lineage/trace 的 stage 消歧参数，label 为表内字段名。
 */
const DR_BATCH_TYPES = [
  { value: 'fermentation', label: '发酵批' },
  { value: 'extraction', label: '萃取批' },
  { value: 'chromatography', label: '层析及一次结晶' },
  { value: 'first_refinement', label: '一次精制' },
  { value: 'second_refinement', label: '二次精制' },
  { value: 'third_refinement', label: '三次精制' },
  { value: 'fourth_refinement', label: '四次精制' },
]

/** 各工段页追溯下拉字段（value → 后端 stage；投料批次/投入批次为该行 feed_batch_no，属上游产出批） */
const FIELD_OPTIONS_BY_MODULE: Record<string, { value: string; label: string }[]> = {
  // 过滤萃取：批号（主批号/发酵批）、萃取批号
  extraction: [
    { value: 'fermentation', label: '批号' },
    { value: 'extraction', label: '萃取批号' },
  ],
  // 层析及一次结晶：发酵液批号、层析生产批号、萃取批号、一次湿粉生产批号
  chromatography: [
    { value: 'fermentation', label: '发酵液批号' },
    { value: 'chromatography', label: '层析生产批号' },
    { value: 'extraction', label: '萃取批号' },
    { value: 'first_refinement', label: '一次湿粉生产批号' },
  ],
  // 一次精制：发酵液批号、生产批号
  first_refinement: [
    { value: 'fermentation', label: '发酵液批号' },
    { value: 'first_refinement', label: '生产批号' },
  ],
  // 二次精制：发酵液批号、生产批号、投料批次（feed=DR-F1 一次湿粉批）
  second_refinement: [
    { value: 'fermentation', label: '发酵液批号' },
    { value: 'second_refinement', label: '生产批号' },
    { value: 'first_refinement', label: '投料批次' },
  ],
  // 三次精制：发酵液批号、生产批号、投入批次（feed=DR-F2 二次湿粉批）
  third_refinement: [
    { value: 'fermentation', label: '发酵液批号' },
    { value: 'third_refinement', label: '生产批号' },
    { value: 'second_refinement', label: '投入批次' },
  ],
  // 四次精制：发酵液批号、生产批号、投入批次（feed=DR-F3 三次湿粉批）
  fourth_refinement: [
    { value: 'fermentation', label: '发酵液批号' },
    { value: 'fourth_refinement', label: '生产批号' },
    { value: 'third_refinement', label: '投入批次' },
  ],
}

/** 按工段页取字段选项；未配置的模块回退为全部工段类型 */
export function getDRFieldOptions(module: string) {
  return FIELD_OPTIONS_BY_MODULE[module] || DR_BATCH_TYPES
}

export default DR_BATCH_TYPES
