'use client'

import { Drawer, Table, Typography } from 'antd'
import { QUALITY_LABELS, formatAmount, type Report } from '@/lib/api/energy-ledger'
import styles from './EnergyWorkspace.module.css'

type Basis = NonNullable<Report['totals'][number]['basis']>
type Node = Basis['nodes'][number]

export function EnergyCalculationBasis({ basis, title, unit, onClose }: { basis: Basis | null; title: string; unit: string; onClose: () => void }) {
  const nodes = basis?.nodes ?? []
  const sources = nodes.filter(node => node.reading_type)
  const statusLabels: Record<string, string> = { restricted: '无查看权限', negative_usage: '负用量' }
  const statusLabel = (status: string) => statusLabels[status] || QUALITY_LABELS[status] || status
  function formula(node: Node) {
    const terms = nodes.filter(child => child.parent_id === node.node_id).map(child => `${formatAmount(child.coefficient)} × ${child.name}`)
    return terms.join(node.operation === 'ratio' ? ' ÷ ' : ' + ') || '来源未取得'
  }
  return <Drawer title={`${title} · 计算依据`} open={Boolean(basis)} onClose={onClose} size={960}>
    {basis && <>
      <Typography.Paragraph>依据日期：{basis.usage_date}；用量单位：{unit}。以下为该日纳入本卡片的来源，不代表所有位置或全厂总用量。</Typography.Paragraph>
      <Typography.Title level={5}>原表字段与各位置用量</Typography.Title>
      <div className={styles.mobileCards}>{sources.map(row => <section key={row.node_id} className={styles.mobileEntry}>
        <Typography.Text strong>{row.name}：{formatAmount(row.value)} {unit}</Typography.Text>
        <div>{row.source_sheet && row.source_column ? `${row.source_sheet}!${row.source_column}列` : '未配置原表位置'}</div>
        {(row.reading_dates ?? []).map((day, index) => <div key={`${day}-${index}`}>{day}：{formatAmount(row.reading_values?.[index])}</div>)}
        <div>{row.reading_type === 'direct' ? '当日直接用量' : '次日读数 − 当日读数'}；倍率 {formatAmount(row.multiplier)}；上级系数 {formatAmount(row.coefficient)}</div>
        <div>{statusLabel(row.status)}{row.note && `；${row.note}`}</div>
      </section>)}</div>
      <div className={styles.desktopTable}><Table<Node> rowKey="node_id" dataSource={sources} pagination={false} scroll={{ x: 850 }} columns={[
        { title: '原表字段', render: (_, row) => row.source_sheet && row.source_column ? `${row.source_sheet}!${row.source_column}列` : '未配置原表位置', width: 150 },
        { title: '位置／字段名', dataIndex: 'name', width: 170 },
        { title: '计算读数', render: (_, row) => <>{(row.reading_dates ?? []).map((day, index) => <div key={`${day}-${index}`}>{day}：{formatAmount(row.reading_values?.[index])}</div>)}<div>{row.reading_type === 'direct' ? '当日直接用量' : '次日读数 − 当日读数'}；倍率 {formatAmount(row.multiplier)}</div></>, width: 240 },
        { title: `位置用量（${unit}）`, render: (_, row) => formatAmount(row.value) },
        { title: '上级系数', render: (_, row) => formatAmount(row.coefficient) },
        { title: '状态／修正', render: (_, row) => <>{statusLabel(row.status)}{row.note && <div>{row.note}</div>}</> },
      ]} /></div>
      <Typography.Title level={5}>各级汇总关系</Typography.Title>
      <Table<Node> rowKey="node_id" dataSource={nodes.filter(node => !node.reading_type)} pagination={false} scroll={{ x: 850 }} columns={[
        { title: '汇总指标', dataIndex: 'name', width: 190 },
        { title: '组成', render: (_, row) => formula(row), width: 300 },
        { title: '计算值', render: (_, row) => formatAmount(row.calculated_value) },
        { title: `有效值（${unit}）`, render: (_, row) => formatAmount(row.value) },
        { title: '状态／修正', render: (_, row) => <>{statusLabel(row.status)}{row.note && <div>{row.note}</div>}</> },
      ]} />
    </>}
  </Drawer>
}
