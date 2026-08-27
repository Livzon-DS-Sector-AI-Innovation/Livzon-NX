'use client'

import Link from 'next/link'
import { useMemo, useRef, useState, type ChangeEvent } from 'react'
import { App, Button, Card, Col, Row, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useRouter } from 'next/navigation'

import { importDeclarationProgressWorkbook } from '@/actions/registration'
import { fetchDeclarationProgressWorkbookExport } from '@/lib/api/client/registration'
import { registrationDeclarationProgressSheets } from '@/lib/registration-declaration-progress'
import {
  buildDonutOption,
  buildHorizontalBarOption,
  buildStackedBarOption,
  RegistrationChartCard,
  RegistrationSummaryHero,
} from '@/components/registration'
import type {
  DeclarationProgressSheetDetail,
  DeclarationProgressWorkbookOverview,
} from '@/types/registration'

interface DeclarationProgressDashboardPageProps {
  overview: DeclarationProgressWorkbookOverview
}

interface SheetSummaryRow {
  key: string
  name: string
  path: string
  recordCount: number
  historyCount: number
  columnCount: number
  updateMode: string
}

function buildSheetRows(sheets: DeclarationProgressSheetDetail[]): SheetSummaryRow[] {
  return registrationDeclarationProgressSheets.map((sheet) => {
    const detail = sheets.find((item) => item.sheet_key === sheet.key)
    return {
      key: sheet.key,
      name: sheet.name,
      path: sheet.path,
      recordCount: detail?.summary.total_records || 0,
      historyCount: detail?.summary.total_history_versions || 0,
      columnCount:
        (detail?.summary.main_column_count || 0) + (detail?.summary.child_column_count || 0),
      updateMode: detail?.supports_sub_records ? '持续更新' : '一次填写',
    }
  })
}

interface DashboardRecordMeta {
  sheetKey: string
  sheetName: string
  productName: string
  projectName: string
  marketName: string
  historyCount: number
  newCount: number
  updatedCount: number
}

function normalizeText(value?: string | null): string {
  return (value || '').trim()
}

function getValueByLabel(
  record: DeclarationProgressSheetDetail['records'][number],
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

function countStyleMarks(styleMarks: Record<string, string | null>) {
  let newCount = 0
  let updatedCount = 0

  Object.values(styleMarks).forEach((value) => {
    if (value === 'new') {
      newCount += 1
    }
    if (value === 'updated') {
      updatedCount += 1
    }
  })

  return { newCount, updatedCount }
}

export default function DeclarationProgressDashboardPage({
  overview,
}: DeclarationProgressDashboardPageProps) {
  const router = useRouter()
  const { message } = App.useApp()
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [importingWorkbook, setImportingWorkbook] = useState(false)
  const [exportingWorkbook, setExportingWorkbook] = useState(false)

  const sheetRows = useMemo(() => buildSheetRows(overview.sheets), [overview.sheets])

  const dashboardData = useMemo(() => {
    const recordsMeta: DashboardRecordMeta[] = []
    const productMap = new Map<
      string,
      {
        productName: string
        projects: Set<string>
        markets: Set<string>
        sheets: Set<string>
        internationalCount: number
        domesticCount: number
        newProductCount: number
        gmpCount: number
        fdaCount: number
        updatedCount: number
        newCount: number
      }
    >()
    const projectMap = new Map<
      string,
      {
        projectName: string
        products: Set<string>
        markets: Set<string>
        sheets: Set<string>
        historyCount: number
        updatedCount: number
        newCount: number
      }
    >()
    const marketMap = new Map<
      string,
      {
        marketName: string
        products: Set<string>
        projects: Set<string>
        sheets: Set<string>
        updatedCount: number
        newCount: number
      }
    >()

    for (const sheet of overview.sheets) {
      const labelMap = new Map(sheet.columns.map((column) => [column.label, column.key]))
      const isInternational = sheet.sheet_key.includes('international')
      const isDomestic = sheet.sheet_key.includes('domestic')
      const isNewProduct = sheet.sheet_key === 'new-product-projects'
      const isGmp = sheet.sheet_key === 'gmp-projects'
      const isFda = sheet.sheet_key === 'us-fda-progress'

      for (const record of sheet.records) {
        const pick = getValueByLabel(record, labelMap)
        const productName =
          pick(['产品', '产品名称', '涉及产品']) || '未填写产品'
        const projectName =
          pick(['项目名称', '产品名称', '涉及产品']) || productName || `记录 ${record.sequence}`
        const marketName =
          pick(['国家/受理机构', '受理机构', '申报机构', '官方机构/国家']) ||
          (sheet.sheet_key === 'us-fda-progress' ? '美国FDA' : '未填写市场/受理机构')
        const { newCount, updatedCount } = countStyleMarks(record.latest_style_marks)

        recordsMeta.push({
          sheetKey: sheet.sheet_key,
          sheetName: sheet.sheet_name,
          productName,
          projectName,
          marketName,
          historyCount: record.history_count,
          newCount,
          updatedCount,
        })

        const productSummary = productMap.get(productName) || {
          productName,
          projects: new Set<string>(),
          markets: new Set<string>(),
          sheets: new Set<string>(),
          internationalCount: 0,
          domesticCount: 0,
          newProductCount: 0,
          gmpCount: 0,
          fdaCount: 0,
          updatedCount: 0,
          newCount: 0,
        }
        productSummary.projects.add(projectName)
        productSummary.markets.add(marketName)
        productSummary.sheets.add(sheet.sheet_name)
        productSummary.internationalCount += isInternational ? 1 : 0
        productSummary.domesticCount += isDomestic ? 1 : 0
        productSummary.newProductCount += isNewProduct ? 1 : 0
        productSummary.gmpCount += isGmp ? 1 : 0
        productSummary.fdaCount += isFda ? 1 : 0
        productSummary.updatedCount += updatedCount
        productSummary.newCount += newCount
        productMap.set(productName, productSummary)

        const projectSummary = projectMap.get(projectName) || {
          projectName,
          products: new Set<string>(),
          markets: new Set<string>(),
          sheets: new Set<string>(),
          historyCount: 0,
          updatedCount: 0,
          newCount: 0,
        }
        projectSummary.products.add(productName)
        projectSummary.markets.add(marketName)
        projectSummary.sheets.add(sheet.sheet_name)
        projectSummary.historyCount += record.history_count
        projectSummary.updatedCount += updatedCount
        projectSummary.newCount += newCount
        projectMap.set(projectName, projectSummary)

        const marketSummary = marketMap.get(marketName) || {
          marketName,
          products: new Set<string>(),
          projects: new Set<string>(),
          sheets: new Set<string>(),
          updatedCount: 0,
          newCount: 0,
        }
        marketSummary.products.add(productName)
        marketSummary.projects.add(projectName)
        marketSummary.sheets.add(sheet.sheet_name)
        marketSummary.updatedCount += updatedCount
        marketSummary.newCount += newCount
        marketMap.set(marketName, marketSummary)
      }
    }

    const productRows = Array.from(productMap.values())
      .map((item) => ({
        key: item.productName,
        productName: item.productName,
        projectCount: item.projects.size,
        marketCount: item.markets.size,
        sheetCount: item.sheets.size,
        updatedCount: item.updatedCount,
        newCount: item.newCount,
        internationalCount: item.internationalCount,
        domesticCount: item.domesticCount,
        newProductCount: item.newProductCount,
        gmpCount: item.gmpCount,
        fdaCount: item.fdaCount,
      }))
      .sort((a, b) => {
        if (b.projectCount !== a.projectCount) {
          return b.projectCount - a.projectCount
        }
        return b.updatedCount + b.newCount - (a.updatedCount + a.newCount)
      })

    const projectRows = Array.from(projectMap.values())
      .map((item) => ({
        key: item.projectName,
        projectName: item.projectName,
        productCount: item.products.size,
        marketCount: item.markets.size,
        sheetCount: item.sheets.size,
        historyCount: item.historyCount,
        updatedCount: item.updatedCount,
        newCount: item.newCount,
      }))
      .sort((a, b) => {
        if (b.updatedCount !== a.updatedCount) {
          return b.updatedCount - a.updatedCount
        }
        return b.newCount - a.newCount
      })

    const marketRows = Array.from(marketMap.values())
      .map((item) => ({
        key: item.marketName,
        marketName: item.marketName,
        productCount: item.products.size,
        projectCount: item.projects.size,
        sheetCount: item.sheets.size,
        updatedCount: item.updatedCount,
        newCount: item.newCount,
      }))
      .sort((a, b) => {
        if (b.projectCount !== a.projectCount) {
          return b.projectCount - a.projectCount
        }
        return b.updatedCount + b.newCount - (a.updatedCount + a.newCount)
      })

    return {
      productRows,
      projectRows,
      marketRows,
      topProduct: productRows[0]?.productName || '暂无',
      topProductProjectCount: productRows[0]?.projectCount || 0,
      topMarket: marketRows[0]?.marketName || '暂无',
      topMarketProjectCount: marketRows[0]?.projectCount || 0,
      updateEventCount: projectRows.reduce((sum, item) => sum + item.updatedCount, 0),
      newEventCount: projectRows.reduce((sum, item) => sum + item.newCount, 0),
      productCategoryChartRows: productRows.slice(0, 12).map((item) => ({
        name: item.productName,
        values: {
          international: item.internationalCount,
          domestic: item.domesticCount,
          newProduct: item.newProductCount,
          gmp: item.gmpCount,
          fda: item.fdaCount,
        },
      })),
      marketProjectChartData: marketRows.slice(0, 12).map((item) => ({
        name: item.marketName,
        value: item.projectCount,
      })),
      projectChangeChartRows: projectRows.slice(0, 12).map((item) => ({
        name: item.projectName,
        values: {
          updated: item.updatedCount,
          new: item.newCount,
        },
      })),
      sheetRecordChartData: sheetRows.map((item) => ({
        name: item.name,
        value: item.recordCount,
      })),
      categorySummaryData: [
        {
          name: '国际项目',
          value: productRows.reduce((sum, item) => sum + item.internationalCount, 0),
        },
        {
          name: '国内项目',
          value: productRows.reduce((sum, item) => sum + item.domesticCount, 0),
        },
        {
          name: '新产品',
          value: productRows.reduce((sum, item) => sum + item.newProductCount, 0),
        },
        {
          name: 'GMP项目',
          value: productRows.reduce((sum, item) => sum + item.gmpCount, 0),
        },
        {
          name: 'FDA项目',
          value: productRows.reduce((sum, item) => sum + item.fdaCount, 0),
        },
      ].filter((item) => item.value > 0),
      recordCount: recordsMeta.length,
    }
  }, [overview.sheets, sheetRows])

  const columns: ColumnsType<SheetSummaryRow> = [
    {
      title: '子页面',
      dataIndex: 'name',
      key: 'name',
      width: 280,
      render: (value: string, record) => (
        <Link href={record.path}>
          <Typography.Text strong>{value}</Typography.Text>
        </Link>
      ),
    },
    {
      title: '记录数',
      dataIndex: 'recordCount',
      key: 'recordCount',
      width: 110,
      align: 'center',
    },
    {
      title: '历史版本数',
      dataIndex: 'historyCount',
      key: 'historyCount',
      width: 120,
      align: 'center',
    },
    {
      title: '字段数',
      dataIndex: 'columnCount',
      key: 'columnCount',
      width: 110,
      align: 'center',
    },
    {
      title: '更新方式',
      dataIndex: 'updateMode',
      key: 'updateMode',
      width: 140,
      align: 'center',
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      align: 'center',
      render: (_value, record) => <Link href={record.path}>进入子表</Link>,
    },
  ]

  async function handleWorkbookImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }

    const formData = new FormData()
    formData.append('file', file)
    setImportingWorkbook(true)
    try {
      const result = await importDeclarationProgressWorkbook(formData)
      message.success(
        `导入完成，共导入 ${result?.imported_records ?? 0} 条主记录`
      )
      router.refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '导入失败')
    } finally {
      setImportingWorkbook(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  async function handleWorkbookExport() {
    setExportingWorkbook(true)
    try {
      await fetchDeclarationProgressWorkbookExport()
      message.success('申报进度工作簿已开始下载')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '导出失败')
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
          申报进度
        </Typography.Title>

        <Space>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx"
            style={{ display: 'none' }}
            onChange={handleWorkbookImport}
          />
          <Button loading={importingWorkbook} onClick={() => fileInputRef.current?.click()}>
            导入原始统计表
          </Button>
          <Button type="primary" loading={exportingWorkbook} onClick={handleWorkbookExport}>
            导出 Excel
          </Button>
        </Space>
      </div>

      <RegistrationSummaryHero
        title="注册项目推进总览"
        subtitle={`当前共覆盖 ${dashboardData.productRows.length} 个产品、${dashboardData.marketRows.length} 个市场/受理机构。重点产品为 ${dashboardData.topProduct}，当前关联 ${dashboardData.topProductProjectCount} 个项目；最活跃市场/机构为 ${dashboardData.topMarket}。`}
        metrics={[
          {
            label: '当前产品数',
            value: dashboardData.productRows.length,
            helper: `${dashboardData.recordCount} 条进度记录`,
            accent: '#2563eb',
          },
          {
            label: '当前项目数',
            value: dashboardData.projectRows.length,
            helper: `${dashboardData.topProduct} 关联项目最多`,
            accent: '#14b8a6',
          },
          {
            label: '红字更新',
            value: dashboardData.updateEventCount,
            helper: '反映近期推进变化',
            accent: '#ef4444',
          },
          {
            label: '蓝字新增',
            value: dashboardData.newEventCount,
            helper: `${dashboardData.topMarketProjectCount} 个项目集中在重点市场`,
            accent: '#6366f1',
          },
        ]}
      />

      <Row gutter={[16, 16]}>
        <Col xs={24}>
          <RegistrationChartCard
            title={`产品维度总览（${dashboardData.productRows.length} 个产品 / ${dashboardData.recordCount} 条记录）`}
            subtitle="看哪些产品承担了更多国际、国内、新产品、GMP 和 FDA 项目。"
            hasData={dashboardData.productCategoryChartRows.length > 0}
            option={buildStackedBarOption(dashboardData.productCategoryChartRows, [
              { key: 'international', label: '国际项目', color: '#2563eb' },
              { key: 'domestic', label: '国内项目', color: '#14b8a6' },
              { key: 'newProduct', label: '新产品', color: '#8b5cf6' },
              { key: 'gmp', label: 'GMP项目', color: '#f59e0b' },
              { key: 'fda', label: 'FDA项目', color: '#ef4444' },
            ])}
            height={360}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <RegistrationChartCard
            title="市场 / 受理机构项目量"
            subtitle="看当前项目最集中落在哪些市场与官方机构。"
            hasData={dashboardData.marketProjectChartData.length > 0}
            option={buildHorizontalBarOption(
              dashboardData.marketProjectChartData,
              '#2563eb',
              '项目数'
            )}
          />
        </Col>
        <Col xs={24} xl={12}>
          <RegistrationChartCard
            title="项目更新热度"
            subtitle="用红字更新和蓝字新增识别近期推进最频繁的项目。"
            hasData={dashboardData.projectChangeChartRows.length > 0}
            option={buildStackedBarOption(dashboardData.projectChangeChartRows, [
              { key: 'updated', label: '红字更新', color: '#ef4444' },
              { key: 'new', label: '蓝字新增', color: '#2563eb' },
            ])}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <RegistrationChartCard
            title="项目类型构成"
            subtitle="看当前申报进度主要分布在哪类业务板块。"
            hasData={dashboardData.categorySummaryData.length > 0}
            option={buildDonutOption(dashboardData.categorySummaryData, [
              '#2563eb',
              '#14b8a6',
              '#8b5cf6',
              '#f59e0b',
              '#ef4444',
            ])}
          />
        </Col>
        <Col xs={24} xl={12}>
          <RegistrationChartCard
            title="各子表记录分布"
            subtitle="看 7 个子页中哪几类业务记录量更高。"
            hasData={dashboardData.sheetRecordChartData.length > 0}
            option={buildHorizontalBarOption(
              dashboardData.sheetRecordChartData,
              '#6366f1',
              '记录数'
            )}
          />
        </Col>
      </Row>

      <Card size="small" title="子表入口">
        <Table<SheetSummaryRow>
          rowKey="key"
          size="small"
          columns={columns}
          dataSource={sheetRows}
          pagination={false}
          scroll={{ x: 900 }}
        />
      </Card>
    </Space>
  )
}
