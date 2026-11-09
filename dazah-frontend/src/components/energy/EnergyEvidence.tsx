import { Card, Typography } from 'antd'
import { reviewDetails, sourceComparisonDetails } from './energy-review'
import { formatAmount, QUALITY_LABELS } from '@/lib/api/energy-ledger'

function isEvidence(value: unknown): value is Record<string, unknown> { return Boolean(value && typeof value === 'object' && !Array.isArray(value)) }

export function EnergyEvidence({ value }: { value: unknown }) {
  if (!isEvidence(value)) return null
  const comparison = sourceComparisonDetails(value)
  return <Card size="small">
    {comparison && <p>待核对：原表值 {formatAmount(comparison.reportedValue)}；差异（原表－系统）：{comparison.difference === null ? `无法计算（${QUALITY_LABELS[comparison.calculationStatus] || comparison.calculationStatus}）` : formatAmount(comparison.difference)}；原表位置：{comparison.source}。已排除在有效汇总和占比之外。</p>}
    {reviewDetails(value).map((review, index) => <p key={index}>待确认：{review.reason}；原表值：{review.reportedValue ?? '未提供'}；依据：{review.source}。已排除在有效汇总和占比之外。</p>)}
    {Array.isArray(value.reading_dates) && <p>读数日期：{value.reading_dates.map(String).join('、')}</p>}
    {Array.isArray(value.reading_values) && <p>原始读数：{value.reading_values.map(item => item === null ? '缺失' : String(item)).join(' → ')}</p>}
    {Array.isArray(value.versions) && <p>原始记录版本：{value.versions.map(String).join('、')}</p>}
    {value.multiplier !== undefined && <p>倍率：{String(value.multiplier)}</p>}
    {value.configuration_version !== undefined && <p>配置版本：{String(value.configuration_version)}</p>}
    {typeof value.business_name === 'string' && <p>业务字段：{String(value.business_sheet ?? value.source_sheet)}·{value.business_name}</p>}
    {typeof value.source_cell === 'string' && <p>原表位置：{String(value.source_sheet)}!{value.source_cell}</p>}
    {typeof value.formula === 'string' && <p>{value.calculation_policy ? '系统公式' : '原表公式'}：<code>{value.formula}</code></p>}
    {typeof value.calculation_date === 'string' && <p>计算日期：{value.calculation_date}（按当天业务日期关联）</p>}
    {isEvidence(value.reference) && <p>参考表留痕：{String(value.reference.source_sheet)}!{String(value.reference.source_cell)}；{value.reference.reported_value != null ? `手填值 ${String(value.reference.reported_value)}` : `原公式 ${String(value.reference.formula ?? '—')}`}。仅供核对，不参与系统计算。</p>}
    {Array.isArray(value.sources) && value.sources.map((source, index) => isEvidence(source) ? <p key={index}>引用：{String(source.sheet)}!{String(source.cell)} ＝ {source.value === null ? '缺失' : String(source.value)}</p> : null)}
    {isEvidence(value.adjustment) && <p>人工调整：{value.adjustment.mode === 'override' ? '覆盖值' : '增减量'} {String(value.adjustment.value)}；依据：{String(value.adjustment.reason)}</p>}
    {Array.isArray(value.source_details) && value.source_details.map((source, index) => isEvidence(source) ? <div key={index}><Typography.Text strong>{String(source.name)} × {String(source.coefficient)} ＝ {source.value === null ? '缺失' : String(source.value)}</Typography.Text><EnergyEvidence value={source.evidence} /></div> : null)}
  </Card>
}
