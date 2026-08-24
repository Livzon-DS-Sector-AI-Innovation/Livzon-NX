'use client'

import { useMemo } from 'react'
import { Col, Row } from 'antd'

import {
  buildDonutOption,
  buildHorizontalBarOption,
  RegistrationChartCard,
  type RegistrationChartDatum,
} from '@/components/registration'
import type { AuthorizationFdaRecord, AuthorizationLedgerRecord } from '@/types/registration'

interface AuthorizationLetterDashboardProps {
  filteredFdaRecords: AuthorizationFdaRecord[]
  filteredLedgerRecords: AuthorizationLedgerRecord[]
}

function buildCountMap(items: Array<string | null | undefined>, fallbackLabel: string): Map<string, number> {
  const counter = new Map<string, number>()

  items.forEach((item) => {
    const label = String(item || '').trim() || fallbackLabel
    counter.set(label, (counter.get(label) || 0) + 1)
  })

  return counter
}

function toSortedChartData(counter: Map<string, number>): RegistrationChartDatum[] {
  return Array.from(counter.entries())
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => {
      if (b.value !== a.value) {
        return b.value - a.value
      }

      return a.name.localeCompare(b.name, 'zh-CN')
    })
}

function buildFdaProductChartData(records: AuthorizationFdaRecord[]): RegistrationChartDatum[] {
  return toSortedChartData(buildCountMap(records.map((item) => item.product_name), '未命名产品'))
}

function buildLedgerProductChartData(records: AuthorizationLedgerRecord[]): RegistrationChartDatum[] {
  return toSortedChartData(buildCountMap(records.map((item) => item.product_name), '未命名产品'))
}

function buildFdaStatusChartData(records: AuthorizationFdaRecord[]): RegistrationChartDatum[] {
  return toSortedChartData(
    buildCountMap(
      records.map((item) => (item.submission_date ? '已递交' : '未递交')),
      '未递交'
    )
  )
}

function buildLedgerStatusChartData(records: AuthorizationLedgerRecord[]): RegistrationChartDatum[] {
  return toSortedChartData(buildCountMap(records.map((item) => item.status), '未设置'))
}

export default function AuthorizationLetterDashboard({
  filteredFdaRecords,
  filteredLedgerRecords,
}: AuthorizationLetterDashboardProps) {
  const fdaProductData = useMemo(
    () => buildFdaProductChartData(filteredFdaRecords),
    [filteredFdaRecords]
  )
  const ledgerProductData = useMemo(
    () => buildLedgerProductChartData(filteredLedgerRecords),
    [filteredLedgerRecords]
  )
  const fdaStatusData = useMemo(
    () => buildFdaStatusChartData(filteredFdaRecords),
    [filteredFdaRecords]
  )
  const ledgerStatusData = useMemo(
    () => buildLedgerStatusChartData(filteredLedgerRecords),
    [filteredLedgerRecords]
  )

  const fdaProductSubtitle = useMemo(() => {
    return `当前筛选下共 ${filteredFdaRecords.length} 条 FDA 授权，覆盖 ${fdaProductData.length} 个产品`
  }, [fdaProductData.length, filteredFdaRecords.length])

  const ledgerProductSubtitle = useMemo(() => {
    return `当前筛选下共 ${filteredLedgerRecords.length} 条市场授权主记录，覆盖 ${ledgerProductData.length} 个产品`
  }, [filteredLedgerRecords.length, ledgerProductData.length])

  const fdaStatusSubtitle = useMemo(() => {
    const submittedCount = filteredFdaRecords.filter((item) => item.submission_date).length
    const pendingCount = filteredFdaRecords.length - submittedCount
    return `已递交 ${submittedCount} 条，未递交 ${pendingCount} 条`
  }, [filteredFdaRecords])

  const ledgerStatusSubtitle = useMemo(() => {
    const submittedCount = filteredLedgerRecords.filter((item) => item.status === '已递交').length
    const pendingCount = filteredLedgerRecords.filter((item) => item.status === '未递交').length
    return `已递交 ${submittedCount} 条，未递交 ${pendingCount} 条`
  }, [filteredLedgerRecords])

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={12}>
        <RegistrationChartCard
          title="FDA 各产品授权分布"
          subtitle={fdaProductSubtitle}
          option={buildHorizontalBarOption(fdaProductData, '#2563eb', 'FDA授权数')}
          hasData={fdaProductData.length > 0}
          height={280}
        />
      </Col>
      <Col xs={24} xl={12}>
        <RegistrationChartCard
          title="市场授权各产品分布"
          subtitle={ledgerProductSubtitle}
          option={buildHorizontalBarOption(ledgerProductData, '#7c3aed', '市场授权数')}
          hasData={ledgerProductData.length > 0}
          height={280}
        />
      </Col>
      <Col xs={24} xl={12}>
        <RegistrationChartCard
          title="FDA 状态分布"
          subtitle={fdaStatusSubtitle}
          option={buildDonutOption(fdaStatusData, ['#2563eb', '#94a3b8'])}
          hasData={fdaStatusData.length > 0}
          height={260}
        />
      </Col>
      <Col xs={24} xl={12}>
        <RegistrationChartCard
          title="市场授权状态分布"
          subtitle={ledgerStatusSubtitle}
          option={buildDonutOption(ledgerStatusData, ['#7c3aed', '#14b8a6', '#f59e0b', '#ef4444', '#94a3b8'])}
          hasData={ledgerStatusData.length > 0}
          height={260}
        />
      </Col>
    </Row>
  )
}
