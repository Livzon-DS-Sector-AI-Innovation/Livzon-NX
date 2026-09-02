'use client'

import Link from 'next/link'
import { useMemo } from 'react'
import { Button, Card, Col, Row, Space, Tag, Typography } from 'antd'

import {
  buildDonutOption,
  buildHorizontalBarOption,
  buildStackedBarOption,
  RegistrationChartCard,
  RegistrationSummaryHero,
  type RegistrationChartDatum,
  type RegistrationMetricItem,
  type RegistrationStackedChartDatum,
} from '@/components/registration'
import type { CertificateSheetSummary, CertificateWorkbookOverview } from '@/types/registration'

interface CertificateManagementDashboardProps {
  overview: CertificateWorkbookOverview
}

function toChartData(
  sheets: CertificateSheetSummary[],
  getValue: (sheet: CertificateSheetSummary) => number
): RegistrationChartDatum[] {
  return [...sheets]
    .map((sheet) => ({
      name: sheet.sheet_name,
      value: getValue(sheet),
    }))
    .sort((a, b) => {
      if (b.value !== a.value) {
        return b.value - a.value
      }

      return a.name.localeCompare(b.name, 'zh-CN')
    })
}

function toRiskStructureData(sheets: CertificateSheetSummary[]): RegistrationStackedChartDatum[] {
  return [...sheets]
    .map((sheet) => {
      const validCount = Math.max(sheet.total_records - sheet.expired_count - sheet.due_90_count, 0)

      return {
        name: sheet.sheet_name,
        values: {
          expired: sheet.expired_count,
          dueSoon: sheet.due_90_count,
          valid: validCount,
        },
      }
    })
    .sort((a, b) => {
      const riskA = (a.values.expired || 0) + (a.values.dueSoon || 0)
      const riskB = (b.values.expired || 0) + (b.values.dueSoon || 0)

      if (riskB !== riskA) {
        return riskB - riskA
      }

      return a.name.localeCompare(b.name, 'zh-CN')
    })
}

function buildDashboardMetrics(overview: CertificateWorkbookOverview): RegistrationMetricItem[] {
  return [
    {
      label: '证书总量',
      value: overview.total_records,
      helper: `覆盖 ${overview.sheet_count} 个证书板块`,
      accent: '#2563eb',
    },
    {
      label: '发证机构覆盖',
      value: overview.issuer_count,
      helper: '用于领导查看机构覆盖广度',
      accent: '#7c3aed',
    },
    {
      label: '产品覆盖范围',
      value: overview.product_count,
      helper: `累计页数 ${overview.total_pages || 0}`,
      accent: '#0f766e',
    },
    {
      label: '到期风险',
      value: overview.expired_count,
      helper: `另有 ${overview.due_90_count} 份将在 90 天内到期`,
      accent: '#dc2626',
    },
  ]
}

function buildRiskLevel(sheet: CertificateSheetSummary): { label: string; color: string } {
  if (sheet.expired_count > 0) {
    return { label: '需立即跟进', color: 'error' }
  }

  if (sheet.due_90_count > 0) {
    return { label: '近期关注', color: 'warning' }
  }

  return { label: '状态稳定', color: 'success' }
}

export default function CertificateManagementDashboard({
  overview,
}: CertificateManagementDashboardProps) {
  const summaryMetrics = useMemo(() => buildDashboardMetrics(overview), [overview])

  const sheetVolumeData = useMemo(
    () => toChartData(overview.sheet_summaries, (sheet) => sheet.total_records),
    [overview.sheet_summaries]
  )

  const coverageData = useMemo(
    () =>
      [...overview.sheet_summaries]
        .map((sheet) => ({
          name: sheet.sheet_name,
          values: {
            issuerCount: sheet.issuer_count,
            productCount: sheet.product_count,
          },
        }))
        .sort((a, b) => {
          const totalA = (a.values.issuerCount || 0) + (a.values.productCount || 0)
          const totalB = (b.values.issuerCount || 0) + (b.values.productCount || 0)

          if (totalB !== totalA) {
            return totalB - totalA
          }

          return a.name.localeCompare(b.name, 'zh-CN')
        }),
    [overview.sheet_summaries]
  )

  const riskStructureData = useMemo(
    () => toRiskStructureData(overview.sheet_summaries),
    [overview.sheet_summaries]
  )

  const expiryStatusData = useMemo(
    () =>
      [
        { name: '有效', value: Math.max(overview.total_records - overview.expired_count - overview.due_90_count, 0) },
        { name: '90天内到期', value: overview.due_90_count },
        { name: '已过期', value: overview.expired_count },
      ].filter((item) => item.value > 0),
    [overview.due_90_count, overview.expired_count, overview.total_records]
  )

  const riskSubtitle = useMemo(() => {
    if (overview.expired_count > 0) {
      return `当前已有 ${overview.expired_count} 份证书过期，需优先补齐续证动作。`
    }

    if (overview.due_90_count > 0) {
      return `当前暂无过期证书，但有 ${overview.due_90_count} 份证书进入 90 天预警窗口。`
    }

    return '当前未发现到期风险，整体证书状态稳定。'
  }, [overview.due_90_count, overview.expired_count])

  const heroSubtitle = useMemo(() => {
    const updatedText = overview.updated_at ? `数据更新时间：${overview.updated_at}` : '数据按当前台账实时汇总'
    return `${updatedText}。${riskSubtitle}`
  }, [overview.updated_at, riskSubtitle])

  const focusSheets = useMemo(
    () =>
      [...overview.sheet_summaries].sort((a, b) => {
        const riskA = a.expired_count * 100 + a.due_90_count * 10 + a.total_records
        const riskB = b.expired_count * 100 + b.due_90_count * 10 + b.total_records

        if (riskB !== riskA) {
          return riskB - riskA
        }

        return a.sheet_name.localeCompare(b.sheet_name, 'zh-CN')
      }),
    [overview.sheet_summaries]
  )

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <RegistrationSummaryHero
        title="证书管理领导总览"
        subtitle={heroSubtitle}
        metrics={summaryMetrics}
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <RegistrationChartCard
            title="各证书板块分布"
            subtitle="按证书存量查看各子表承载规模，便于汇报资源分布"
            option={buildHorizontalBarOption(sheetVolumeData, '#2563eb', '证书数')}
            hasData={sheetVolumeData.length > 0}
            height={300}
          />
        </Col>
        <Col xs={24} xl={12}>
          <RegistrationChartCard
            title="整体到期风险分布"
            subtitle="汇总全台账证书有效、预警与过期状态"
            option={buildDonutOption(expiryStatusData, ['#1aae39', '#dd5b00', '#e03131'])}
            hasData={expiryStatusData.length > 0}
            height={300}
          />
        </Col>
        <Col xs={24} xl={12}>
          <RegistrationChartCard
            title="各板块到期结构"
            subtitle="对比各子表的过期、90天内到期和有效证书结构"
            option={buildStackedBarOption(riskStructureData, [
              { key: 'expired', label: '已过期', color: '#e03131' },
              { key: 'dueSoon', label: '90天内到期', color: '#dd5b00' },
              { key: 'valid', label: '有效', color: '#1aae39' },
            ])}
            hasData={riskStructureData.length > 0}
            height={320}
          />
        </Col>
        <Col xs={24} xl={12}>
          <RegistrationChartCard
            title="板块覆盖能力"
            subtitle="横向比较各子表的发证机构覆盖和产品覆盖范围"
            option={buildStackedBarOption(coverageData, [
              { key: 'issuerCount', label: '发证机构数', color: '#7c3aed' },
              { key: 'productCount', label: '产品覆盖数', color: '#14b8a6' },
            ])}
            hasData={coverageData.length > 0}
            height={320}
          />
        </Col>
      </Row>

      <Card
        size="small"
        title="重点板块跟踪"
      >
        <Row gutter={[16, 16]}>
          {focusSheets.map((sheet) => {
            const riskLevel = buildRiskLevel(sheet)

            return (
              <Col xs={24} md={12} xl={6} key={sheet.sheet_key}>
                <Card
                  size="small"
                  styles={{
                    body: {
                      padding: 16,
                      background:
                        'linear-gradient(180deg, rgba(248,250,252,0.98) 0%, rgba(255,255,255,1) 100%)',
                    },
                  }}
                >
                  <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                      <div>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {sheet.sheet_name}
                        </Typography.Text>
                        <Typography.Title level={5} style={{ margin: '6px 0 0' }}>
                          {sheet.title}
                        </Typography.Title>
                      </div>
                      <Tag color={riskLevel.color}>{riskLevel.label}</Tag>
                    </div>

                    <Row gutter={[12, 12]}>
                      <Col span={12}>
                        <div style={{ fontSize: 12, color: 'var(--color-steel)' }}>证书数</div>
                        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--color-charcoal)' }}>{sheet.total_records}</div>
                      </Col>
                      <Col span={12}>
                        <div style={{ fontSize: 12, color: 'var(--color-steel)' }}>发证机构</div>
                        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--color-charcoal)' }}>{sheet.issuer_count}</div>
                      </Col>
                      <Col span={12}>
                        <div style={{ fontSize: 12, color: 'var(--color-steel)' }}>已过期</div>
                        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--color-error, #e03131)' }}>{sheet.expired_count}</div>
                      </Col>
                      <Col span={12}>
                        <div style={{ fontSize: 12, color: 'var(--color-steel)' }}>90天内到期</div>
                        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--color-warning, #dd5b00)' }}>{sheet.due_90_count}</div>
                      </Col>
                    </Row>
                    <Link href={`/registration/certificate-management/${sheet.sheet_key}`}>
                      <Button block type="primary">
                        查看子表
                      </Button>
                    </Link>
                  </Space>
                </Card>
              </Col>
            )
          })}
        </Row>
      </Card>
    </Space>
  )
}
