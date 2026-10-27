'use client'

import { useState } from 'react'
import { Button, Card, Statistic, Typography } from 'antd'
import dayjs from 'dayjs'
import { CATEGORY_LABELS, formatAmount, type Report } from '@/lib/api/energy-ledger'
import styles from './EnergyWorkspace.module.css'
import { EnergyCalculationBasis } from './EnergyCalculationBasis'

function groupKey(row: Report['totals'][number]) {
  return `${row.category}/${row.unit}/${row.quantity_kind}/${row.temperature}`
}

function displayAmount(value: string | null | undefined) {
  return formatAmount(value).replace(/^([+-]?)(\d+)(\.\d+)?$/, (_, sign: string, whole: string, fraction: string | undefined) => `${sign}${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}${fraction ?? ''}`)
}

export function EnergyOverviewCards({ report }: { report: Report }) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const selected = report.totals.find(total => groupKey(total) === selectedKey)
  const periodDays = dayjs(report.end_date).diff(dayjs(report.start_date), 'day') + 1

  return <>
    <div className={styles.overviewGrid}>
      {report.totals.map(total => {
        const name = `${CATEGORY_LABELS[total.category]} ${total.temperature}`.trim()
        const peers = report.totals.filter(row => row.category === total.category && row.temperature === total.temperature)
        const title = peers.length > 1 ? `${name} · 口径 ${peers.indexOf(total) + 1}` : name
        const days = (report.trend ?? []).filter(row => groupKey(row) === groupKey(total) && row.usage_date >= report.start_date && row.usage_date <= report.end_date)
        const validDays = days.filter(row => row.expected_count > 0 && row.available_count === row.expected_count && row.value !== null)
        const latest = validDays.reduce<NonNullable<Report['trend']>[number] | undefined>((last, row) => !last || row.usage_date > last.usage_date ? row : last, undefined)
        const validDayCount = new Set(validDays.map(row => row.usage_date)).size
        const complete = validDayCount === periodDays
        return <Card key={groupKey(total)} classNames={{ body: styles.overviewCard }} aria-label={`${title}用量摘要`}>
          <div className={styles.overviewHeading}><Typography.Title level={5}>{title}</Typography.Title><Typography.Text type={complete ? 'success' : 'warning'}>{complete ? '期间完整' : '期间不完整'}</Typography.Text></div>
          <Typography.Text>统计范围：{Array.from(new Set(total.basis?.nodes.filter(node => node.reading_type || node.status === 'restricted' || node.name === '来源配置缺失').map(node => node.name))).join('、') || '来源未取得，请核对配置'}</Typography.Text>
          <Typography.Text type="secondary">{latest ? `用量日期 ${latest.usage_date}（本项最近完整日）` : '尚无完整日用量'}</Typography.Text>
          <Statistic title="当日用量" value={formatAmount(latest?.value)} formatter={() => displayAmount(latest?.value)} suffix={<span className={styles.overviewUnit}>{total.unit}</span>} />
          <dl className={styles.overviewDetails}>
            <div><dt>期间累计（已有数值）</dt><dd>{displayAmount(total.value)} {total.unit}</dd></div>
            <div><dt>有效天数</dt><dd>{validDayCount} / {periodDays} 天</dd></div>
          </dl>
          <Typography.Text type="secondary">{report.start_date} 至 {report.end_date}</Typography.Text>
          <Typography.Text type="secondary">{complete ? '所选期间每日结果均完整有效' : '期间尚未完整，累计仅供参考'}</Typography.Text>
          <Button type="link" onClick={() => setSelectedKey(groupKey(total))} disabled={!total.basis}>查看计算依据</Button>
        </Card>
      })}
    </div>
    <EnergyCalculationBasis basis={selected?.basis ?? null} title={selected ? `${CATEGORY_LABELS[selected.category]} ${selected.temperature}`.trim() : ''} unit={selected?.unit ?? ''} onClose={() => setSelectedKey(null)} />
  </>
}
