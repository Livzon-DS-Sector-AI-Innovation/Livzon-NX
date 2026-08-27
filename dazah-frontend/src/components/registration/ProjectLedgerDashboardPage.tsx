'use client'

import Link from 'next/link'
import { useMemo, useRef, useState, type ChangeEvent } from 'react'
import { App, Button, Card, Col, Row, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useRouter } from 'next/navigation'

import { importProjectLedgerWorkbook } from '@/actions/registration'
import { fetchProjectLedgerWorkbookExport } from '@/lib/api/client/registration'
import type { ProjectLedgerRecord, ProjectLedgerWorkbookOverview } from '@/types/registration'
import { registrationProjectLedgerSheets } from '@/lib/registration-project-ledger'
import {
  buildHorizontalBarOption,
  buildStackedBarOption,
  RegistrationChartCard,
  RegistrationSummaryHero,
} from '@/components/registration'

interface ProjectLedgerDashboardPageProps {
  overview: ProjectLedgerWorkbookOverview
}

interface DashboardRecordMeta {
  record: ProjectLedgerRecord
  sheetKey: string
  sheetName: string
  productName: string
  projectName: string
  marketName: string
  isInternational: boolean
  isDomestic: boolean
  isAssociatedReview: boolean
  isStandaloneReview: boolean
  isSuccessful: boolean
}

interface SheetSummaryRow {
  key: string
  sheetName: string
  category: string
  reviewMode: string
  totalRecords: number
  successCount: number
  historyCount: number
}

function normalizeText(value?: string | null): string {
  return (value || '').trim()
}

function getValueByLabel(
  record: ProjectLedgerRecord,
  labelMap: Map<string, string>
): (labels: string[]) => string {
  return (labels: string[]) => {
    for (const label of labels) {
      const key = labelMap.get(label)
      if (key) {
        return normalizeText(record.latest_values[key])
      }
    }
    return ''
  }
}

function checkSuccess(meta: {
  certificateStatus: string
  certificateName: string
  resultText: string
  historyText: string
  activityType: string
}) {
  if (meta.certificateStatus === '是') {
    return true
  }
  if (meta.certificateName) {
    return true
  }
  const mergedText = [meta.resultText, meta.historyText, meta.activityType].join(' ')
  return /批准|通过|获证|注册成功|已获批|批准文号|certificate|gmp/i.test(mergedText)
}

export default function ProjectLedgerDashboardPage({
  overview,
}: ProjectLedgerDashboardPageProps) {
  const router = useRouter()
  const { message } = App.useApp()
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [importingWorkbook, setImportingWorkbook] = useState(false)
  const [exportingWorkbook, setExportingWorkbook] = useState(false)

  const dashboardData = useMemo(() => {
    const recordsMeta: DashboardRecordMeta[] = []
    const productMap = new Map<
      string,
      {
        productName: string
        projects: Set<string>
        markets: Set<string>
        sheets: Set<string>
        successCount: number
        internationalCount: number
        domesticCount: number
        associatedCount: number
        standaloneCount: number
      }
    >()
    const projectMap = new Map<
      string,
      {
        projectName: string
        products: Set<string>
        markets: Set<string>
        sheets: Set<string>
        successCount: number
        internationalCount: number
        domesticCount: number
        associatedCount: number
        standaloneCount: number
      }
    >()
    const marketMap = new Map<
      string,
      {
        marketName: string
        products: Set<string>
        projects: Set<string>
        sheets: Set<string>
        successCount: number
        internationalCount: number
        domesticCount: number
      }
    >()

    for (const sheet of overview.sheets) {
      const labelMap = new Map(sheet.columns.map((column) => [column.label, column.key]))
      for (const record of sheet.records) {
        const pick = getValueByLabel(record, labelMap)
        const productName = pick(['产品'])
        const projectName = pick(['项目名称'])
        const marketName = pick(['国家/受理机构', '受理机构'])
        const certificateStatus = pick(['是否获得证书'])
        const certificateName = pick(['证书名称'])
        const resultText = pick(['（该项目）审评结果/批准情况', '（该项目）审评结果/API和制剂分别被批准的时间/正式批准信函或证书情况'])
        const historyText = pick(['与制剂关联审评历史，被官方批准历史'])
        const activityType = pick(['药政活动类型（首次递交/缺陷信回复/变更/年度报告/再注册/委托生产/撤销）'])

        recordsMeta.push({
          record,
          sheetKey: sheet.sheet_key,
          sheetName: sheet.sheet_name,
          productName,
          projectName,
          marketName,
          isInternational: sheet.sheet_key.includes('international'),
          isDomestic: sheet.sheet_key.includes('domestic'),
          isAssociatedReview: sheet.sheet_key.includes('associated'),
          isStandaloneReview: sheet.sheet_key.includes('standalone'),
          isSuccessful: checkSuccess({
            certificateStatus,
            certificateName,
            resultText,
            historyText,
            activityType,
          }),
        })
      }
    }

    const sheetRows: SheetSummaryRow[] = overview.sheets.map((sheet) => {
      const sheetRecords = recordsMeta.filter((item) => item.sheetKey === sheet.sheet_key)
      return {
        key: sheet.sheet_key,
        sheetName: sheet.sheet_name,
        category: sheet.sheet_key.includes('international') ? '国际' : '国内',
        reviewMode: sheet.sheet_key.includes('associated') ? '关联审评' : '单独审评',
        totalRecords: sheet.summary.total_records,
        successCount: sheetRecords.filter((item) => item.isSuccessful).length,
        historyCount: sheet.summary.records_with_history,
      }
    })

    for (const item of recordsMeta) {
      const productKey = item.productName || '未填写产品'
      const projectKey = item.projectName || '未填写项目'
      const marketKey = item.marketName || '未填写市场/受理机构'

      const currentProduct = productMap.get(productKey) || {
        productName: productKey,
        projects: new Set<string>(),
        markets: new Set<string>(),
        sheets: new Set<string>(),
        successCount: 0,
        internationalCount: 0,
        domesticCount: 0,
        associatedCount: 0,
        standaloneCount: 0,
      }
      currentProduct.projects.add(projectKey)
      currentProduct.markets.add(marketKey)
      currentProduct.sheets.add(item.sheetName)
      currentProduct.successCount += item.isSuccessful ? 1 : 0
      currentProduct.internationalCount += item.isInternational ? 1 : 0
      currentProduct.domesticCount += item.isDomestic ? 1 : 0
      currentProduct.associatedCount += item.isAssociatedReview ? 1 : 0
      currentProduct.standaloneCount += item.isStandaloneReview ? 1 : 0
      productMap.set(productKey, currentProduct)

      const currentProject = projectMap.get(projectKey) || {
        projectName: projectKey,
        products: new Set<string>(),
        markets: new Set<string>(),
        sheets: new Set<string>(),
        successCount: 0,
        internationalCount: 0,
        domesticCount: 0,
        associatedCount: 0,
        standaloneCount: 0,
      }
      currentProject.products.add(productKey)
      currentProject.markets.add(marketKey)
      currentProject.sheets.add(item.sheetName)
      currentProject.successCount += item.isSuccessful ? 1 : 0
      currentProject.internationalCount += item.isInternational ? 1 : 0
      currentProject.domesticCount += item.isDomestic ? 1 : 0
      currentProject.associatedCount += item.isAssociatedReview ? 1 : 0
      currentProject.standaloneCount += item.isStandaloneReview ? 1 : 0
      projectMap.set(projectKey, currentProject)

      const currentMarket = marketMap.get(marketKey) || {
        marketName: marketKey,
        products: new Set<string>(),
        projects: new Set<string>(),
        sheets: new Set<string>(),
        successCount: 0,
        internationalCount: 0,
        domesticCount: 0,
      }
      currentMarket.products.add(productKey)
      currentMarket.projects.add(projectKey)
      currentMarket.sheets.add(item.sheetName)
      currentMarket.successCount += item.isSuccessful ? 1 : 0
      currentMarket.internationalCount += item.isInternational ? 1 : 0
      currentMarket.domesticCount += item.isDomestic ? 1 : 0
      marketMap.set(marketKey, currentMarket)
    }

    return {
      recordsMeta,
      totalProducts: productMap.size,
      totalProjects: projectMap.size,
      totalMarkets: marketMap.size,
      successCount: recordsMeta.filter((item) => item.isSuccessful).length,
      internationalCount: recordsMeta.filter((item) => item.isInternational).length,
      domesticCount: recordsMeta.filter((item) => item.isDomestic).length,
      associatedCount: recordsMeta.filter((item) => item.isAssociatedReview).length,
      standaloneCount: recordsMeta.filter((item) => item.isStandaloneReview).length,
      productRows: Array.from(productMap.values())
        .map((item) => ({
          key: item.productName,
          productName: item.productName,
          projectCount: item.projects.size,
          marketCount: item.markets.size,
          sheetCount: item.sheets.size,
          successCount: item.successCount,
          internationalCount: item.internationalCount,
          domesticCount: item.domesticCount,
          associatedCount: item.associatedCount,
          standaloneCount: item.standaloneCount,
        }))
        .sort((a, b) => {
          if (b.projectCount !== a.projectCount) {
            return b.projectCount - a.projectCount
          }
          return b.successCount - a.successCount
        }),
      projectRows: Array.from(projectMap.values())
        .map((item) => ({
          key: item.projectName,
          projectName: item.projectName,
          productCount: item.products.size,
          marketCount: item.markets.size,
          sheetCount: item.sheets.size,
          successCount: item.successCount,
          internationalCount: item.internationalCount,
          domesticCount: item.domesticCount,
          associatedCount: item.associatedCount,
          standaloneCount: item.standaloneCount,
        }))
        .sort((a, b) => {
          if (b.successCount !== a.successCount) {
            return b.successCount - a.successCount
          }
          return b.marketCount - a.marketCount
        }),
      marketRows: Array.from(marketMap.values())
        .map((item) => ({
          key: item.marketName,
          marketName: item.marketName,
          productCount: item.products.size,
          projectCount: item.projects.size,
          sheetCount: item.sheets.size,
          successCount: item.successCount,
          internationalCount: item.internationalCount,
          domesticCount: item.domesticCount,
        }))
        .sort((a, b) => {
          if (b.projectCount !== a.projectCount) {
            return b.projectCount - a.projectCount
          }
          return b.successCount - a.successCount
        }),
      productScopeChartRows: Array.from(productMap.values())
        .map((item) => ({
          name: item.productName,
          values: {
            international: item.internationalCount,
            domestic: item.domesticCount,
          },
        }))
        .sort(
          (a, b) =>
            b.values.international + b.values.domestic - (a.values.international + a.values.domestic)
        )
        .slice(0, 12),
      productReviewChartRows: Array.from(productMap.values())
        .map((item) => ({
          name: item.productName,
          values: {
            associated: item.associatedCount,
            standalone: item.standaloneCount,
          },
        }))
        .sort(
          (a, b) =>
            b.values.associated + b.values.standalone - (a.values.associated + a.values.standalone)
        )
        .slice(0, 12),
      marketProjectChartData: Array.from(marketMap.values())
        .map((item) => ({
          name: item.marketName,
          value: item.projects.size,
        }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 12),
      projectSuccessChartData: Array.from(projectMap.values())
        .map((item) => ({
          name: item.projectName,
          value: item.successCount,
        }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 12),
      sheetSuccessChartRows: sheetRows.map((item) => ({
        name: item.sheetName,
        values: {
          success: item.successCount,
          pending: Math.max(item.totalRecords - item.successCount, 0),
        },
      })),
      topProduct:
        Array.from(productMap.values())
          .sort((a, b) => b.projects.size - a.projects.size)[0]?.productName || '暂无',
      topMarket:
        Array.from(marketMap.values())
          .sort((a, b) => b.projects.size - a.projects.size)[0]?.marketName || '暂无',
      sheetRows,
    }
  }, [overview])

  const sheetColumns: ColumnsType<SheetSummaryRow> = [
    {
      title: '子页',
      dataIndex: 'sheetName',
      key: 'sheetName',
      render: (value: string, record) => {
        const link = registrationProjectLedgerSheets.find((item) => item.key === record.key)
        return link ? (
          <Link href={link.path}>
            <Typography.Text strong>{value}</Typography.Text>
          </Link>
        ) : (
          <Typography.Text strong>{value}</Typography.Text>
        )
      },
    },
    {
      title: '国内/国外',
      dataIndex: 'category',
      key: 'category',
      width: 100,
      align: 'center',
      render: (value: string) => <Tag color={value === '国际' ? 'blue' : 'gold'}>{value}</Tag>,
    },
    {
      title: '审批模式',
      dataIndex: 'reviewMode',
      key: 'reviewMode',
      width: 120,
      align: 'center',
    },
    {
      title: '记录数',
      dataIndex: 'totalRecords',
      key: 'totalRecords',
      width: 90,
      align: 'center',
    },
    {
      title: '成功数',
      dataIndex: 'successCount',
      key: 'successCount',
      width: 90,
      align: 'center',
    },
    {
      title: '有历史',
      dataIndex: 'historyCount',
      key: 'historyCount',
      width: 90,
      align: 'center',
    },
  ]

  async function handleWorkbookImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) {
      return
    }

    const formData = new FormData()
    formData.append('file', file)
    setImportingWorkbook(true)
    try {
      const result = await importProjectLedgerWorkbook(formData)
      message.success(
        result
          ? `导入成功，已覆盖写入 ${result.imported_records} 条申报台账记录`
          : '导入成功'
      )
      router.refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '申报台账导入失败')
    } finally {
      setImportingWorkbook(false)
    }
  }

  async function handleWorkbookExport() {
    setExportingWorkbook(true)
    try {
      await fetchProjectLedgerWorkbookExport()
      message.success('申报台账导出成功')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '申报台账导出失败')
    } finally {
      setExportingWorkbook(false)
    }
  }

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        <Typography.Title level={3} style={{ marginBottom: 0 }}>
          申报台账
        </Typography.Title>

        <Space>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx"
            hidden
            onChange={handleWorkbookImport}
          />
          <Button onClick={() => fileInputRef.current?.click()} loading={importingWorkbook}>
            导入申报台账
          </Button>
          <Button type="primary" onClick={handleWorkbookExport} loading={exportingWorkbook}>
            导出申报台账
          </Button>
        </Space>
      </div>

      <RegistrationSummaryHero
        title="注册台账汇报看板"
        subtitle={`当前台账覆盖 ${dashboardData.totalProducts} 个产品、${dashboardData.totalProjects} 个项目、${dashboardData.totalMarkets} 个市场/受理机构。重点产品为 ${dashboardData.topProduct}，重点市场/机构为 ${dashboardData.topMarket}。`}
        metrics={[
          {
            label: '产品覆盖',
            value: dashboardData.totalProducts,
            helper: `${dashboardData.totalProjects} 个项目在跟踪`,
            accent: '#2563eb',
          },
          {
            label: '成功记录',
            value: dashboardData.successCount,
            helper: '已批准 / 已获证 / 已通过',
            accent: '#059669',
          },
          {
            label: '国际 / 国内',
            value: `${dashboardData.internationalCount} / ${dashboardData.domesticCount}`,
            helper: '看注册布局重心',
            accent: '#14b8a6',
          },
          {
            label: '关联 / 单独',
            value: `${dashboardData.associatedCount} / ${dashboardData.standaloneCount}`,
            helper: '看审评模式分布',
            accent: '#8b5cf6',
          },
        ]}
      />

      <Row gutter={[16, 16]}>
        <Col xs={24}>
          <RegistrationChartCard
            title={`产品维度总览（${dashboardData.totalProducts} 个产品 / 国际 ${dashboardData.internationalCount} / 国内 ${dashboardData.domesticCount}）`}
            subtitle="看各产品在国际与国内注册上的布局差异。"
            hasData={dashboardData.productScopeChartRows.length > 0}
            option={buildStackedBarOption(dashboardData.productScopeChartRows, [
              { key: 'international', label: '国际', color: '#2563eb' },
              { key: 'domestic', label: '国内', color: '#14b8a6' },
            ])}
            height={360}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <RegistrationChartCard
            title={`产品审批模式（关联 ${dashboardData.associatedCount} / 单独 ${dashboardData.standaloneCount}）`}
            subtitle="看重点产品更多走关联审评还是单独审评。"
            hasData={dashboardData.productReviewChartRows.length > 0}
            option={buildStackedBarOption(dashboardData.productReviewChartRows, [
              { key: 'associated', label: '关联审评', color: '#8b5cf6' },
              { key: 'standalone', label: '单独审评', color: '#f59e0b' },
            ])}
          />
        </Col>
        <Col xs={24} xl={12}>
          <RegistrationChartCard
            title="市场 / 受理机构项目量"
            subtitle="看项目主要集中在哪些市场、机构与国家。"
            hasData={dashboardData.marketProjectChartData.length > 0}
            option={buildHorizontalBarOption(
              dashboardData.marketProjectChartData,
              '#2563eb',
              '项目数'
            )}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <RegistrationChartCard
            title={`项目成功分布（${dashboardData.totalProjects} 个项目 / ${dashboardData.successCount} 条成功记录）`}
            subtitle="看当前已经形成较多成功结果的项目。"
            hasData={dashboardData.projectSuccessChartData.length > 0}
            option={buildHorizontalBarOption(
              dashboardData.projectSuccessChartData,
              '#059669',
              '成功数'
            )}
          />
        </Col>
        <Col xs={24} xl={12}>
          <RegistrationChartCard
            title="四类台账完成情况"
            subtitle="看四类台账里成功数与进行中项目的对比。"
            hasData={dashboardData.sheetSuccessChartRows.length > 0}
            option={buildStackedBarOption(dashboardData.sheetSuccessChartRows, [
              { key: 'success', label: '成功数', color: '#059669' },
              { key: 'pending', label: '进行中', color: '#cbd5e1' },
            ])}
          />
        </Col>
      </Row>

      <Card size="small" title="四类申报台账总览">
        <Table<SheetSummaryRow>
          rowKey="key"
          size="small"
          pagination={false}
          dataSource={dashboardData.sheetRows}
          columns={sheetColumns}
        />
      </Card>
    </Space>
  )
}
