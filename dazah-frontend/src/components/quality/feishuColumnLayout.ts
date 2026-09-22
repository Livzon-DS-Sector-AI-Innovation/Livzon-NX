import type { ColumnsType } from 'antd/es/table'

// 仅用于关联飞书表格的页面；偏差台账使用本地数据和原有列布局。
// 这里只投影已有列，不改变取值、渲染或操作逻辑。
// 未列出的业务字段仍由原有详情页面展示。
export const feishuColumnLayouts = {
  deviationReport: ['偏差编号', '报告时间', '偏差内容', '涉及产品名称/批号', '附件', '部门', '报告人', '部门负责人', '部门负责人确认', '部门负责人确认时间', 'QA', 'QA确认', 'QA确认时间', 'QA负责人', 'QA负责人确认', 'QA负责人确认时间', '报告状态'],
  deviationInvestigation: ['偏差编号', '第N次推送', '偏差调查报告', '提交日期', '部门', '提交人', '部门负责人', '部门负责人审核结果', '部门负责人审核时间', 'QA', 'QA审核结果', 'QA审核时间', 'QA负责人', 'QA负责人审核结果', 'QA负责人审核时间', '流程状态', '已退回待重新提交'],
  capaLedger: ['CAPA编号', '启动日期', '事件部门', '涉及产品', 'CAPA简述', 'CAPA效果评估', '关闭日期', 'QA质量员', 'QA质量员确认日期', 'CAPA状态', '关联CAPA计划'],
  capaPlan: ['CAPA编号', '计划内容', '预计完成时间', '责任人', '部门', '部门负责人', '责任人确认', '部门负责人确认', '进度', '提醒状态', '关联CAPA编号'],
  oosReport: ['报告时间', '内容', '涉及产品名称', '涉及批号', '附件', '报告部门', '报告人', '部门负责人', '部门负责人确认', '涉及发酵负责人', '涉及发酵负责人确认', '涉及提炼负责人', '涉及提炼负责人确认', 'QA', 'QA确认', 'QA负责人', 'QA负责人确认'],
  oosInvestigation: ['OOS/OOT编号', '第N次推送', '调查报告', '提交日期', '部门', '提交人', '部门负责人', '部门负责人审核结果', '部门负责人审核时间', 'QA', 'QA审核结果', 'QA审核时间', 'QA负责人', 'QA负责人审核结果', 'QA负责人审核时间', '流程状态', '已退回待重新提交', '部门负责人(直接)'],
  oosLedger: ['序号', '日期', '物料名称', '批号', '调查编号', '问题描述', '产生原因', '纠正预防措施', '最终处理结果', '登记人', '备注'],
  productDepartment: ['序号', '产品代码', '涉及发酵部门', '涉及发酵部门负责人', '涉及提炼部门', '涉及提炼部门负责人'],
} as const

export function alignFeishuColumns<T extends object>(
  columns: ColumnsType<T>,
  layout: readonly string[],
  renamed: Record<string, string> = {},
): ColumnsType<T> {
  const named = columns.map(column => {
    const title = renamed[String(column.key)]
    return title ? { ...column, title } : column
  })
  return [
    ...layout.flatMap(title => named.filter(column => column.title === title)),
    ...named.filter(column => column.title === '操作'),
  ]
}
