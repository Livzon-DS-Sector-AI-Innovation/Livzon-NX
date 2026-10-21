import { Typography } from 'antd'
import styles from './EnergyWorkspace.module.css'

function isEvidence(value: unknown): value is Record<string, unknown> { return Boolean(value && typeof value === 'object' && !Array.isArray(value)) }

export function EnergyEvidence({ value }: { value: unknown }) {
  if (!isEvidence(value)) return null
  return <section className={styles.surface}>
    {Array.isArray(value.reading_dates) && <p>读数日期：{value.reading_dates.map(String).join('、')}</p>}
    {Array.isArray(value.reading_values) && <p>原始读数：{value.reading_values.map(item => item === null ? '缺失' : String(item)).join(' → ')}</p>}
    {Array.isArray(value.versions) && <p>原始记录版本：{value.versions.map(String).join('、')}</p>}
    {value.multiplier !== undefined && <p>倍率：{String(value.multiplier)}</p>}
    {value.configuration_version !== undefined && <p>配置版本：{String(value.configuration_version)}</p>}
    {isEvidence(value.adjustment) && <p>人工调整：{value.adjustment.mode === 'override' ? '覆盖值' : '增减量'} {String(value.adjustment.value)}；依据：{String(value.adjustment.reason)}</p>}
    {Array.isArray(value.source_details) && value.source_details.map((source, index) => isEvidence(source) ? <div key={index}><Typography.Text strong>{String(source.name)} × {String(source.coefficient)} ＝ {source.value === null ? '缺失' : String(source.value)}</Typography.Text><EnergyEvidence value={source.evidence} /></div> : null)}
  </section>
}
