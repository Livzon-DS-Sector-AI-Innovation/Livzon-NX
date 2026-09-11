'use client'

import { useEffect, useMemo, useState } from 'react'
import { App, Alert, Button, Card, Col, Row, Select, Space, Statistic, Table, Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { LinkOutlined, MessageOutlined, RightOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import dayjs from 'dayjs'
import ReactECharts from 'echarts-for-react'
import {
  fetchAnomalyAnalysisStatus,
  fetchAnomalyDashboard,
  fetchAnomalyReportYears,
} from '@/lib/api/client/quality'
import type { AnomalyDashboardData, AnomalyOpenRecord } from '@/types/quality'
import { runAnomalyAnalysisAction } from '@/actions/finished-product-anomaly'
import { FinishedProductAnomalyChat } from './FinishedProductAnomalyChat'

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message
  return fallback
}

/** 成品异常仪表盘：按产品×异常类型的 AI 分类聚合视图。 */
export function FinishedProductAnomalyDashboard() {
  const router = useRouter()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [yearFilter, setYearFilter] = useState<number | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = useState(false)

  const yearsQuery = useQuery({
    queryKey: ['anomaly-report', 'years'],
    queryFn: fetchAnomalyReportYears,
  })
  const dashQuery = useQuery({
    queryKey: ['anomaly-report', 'dashboard', yearFilter],
    queryFn: () => fetchAnomalyDashboard(yearFilter ?? undefined),
  })
  const statusQuery = useQuery({
    queryKey: ['anomaly-report', 'analysis-status', jobId],
    queryFn: () => fetchAnomalyAnalysisStatus(jobId as string),
    enabled: jobId !== null,
    refetchInterval: 3000,
  })

  const data: AnomalyDashboardData | undefined = dashQuery.data
  const configuredYears = useMemo(
    () => (yearsQuery.data ?? []).filter((item) => item.table_configured),
    [yearsQuery.data],
  )
  const jobRunning = jobId !== null

  useEffect(() => {
    const status = statusQuery.data
    if (!jobId || !status) return
    if (status.state !== 'completed' && status.state !== 'failed') return
    void (async () => {
      const completed = status.state === 'completed'
      setJobId(null)
      if (completed) {
        message.success(`AI 分类完成，本次分类 ${status.result?.analyzed ?? 0} 条记录`)
        queryClient.invalidateQueries({ queryKey: ['anomaly-report', 'dashboard'] })
      } else {
        message.error(`AI 分析失败：${status.progress || '未知错误'}`)
      }
    })()
  }, [jobId, statusQuery.data, message, queryClient])

  useEffect(() => {
    if (dashQuery.error) {
      message.error(getErrorMessage(dashQuery.error, '加载成品异常仪表盘失败'))
    }
  }, [dashQuery.error, message])

  const handleRunAnalysis = async () => {
    try {
      const result = await runAnomalyAnalysisAction(yearFilter ?? undefined)
      setJobId(result.job_id)
      message.info('AI 分析已启动，完成后图表自动刷新')
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '启动 AI 分析失败'))
    }
  }

  /** 堆叠柱状图：x=产品，series=异常类型 */
  const productChart = useMemo(() => {
    if (!data) return null
    const products = data.products
    const types = data.type_totals.map((item) => item.type)
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { type: 'scroll', top: 0 },
      grid: { left: 40, right: 16, top: 48, bottom: 24 },
      xAxis: {
        type: 'category' as const,
        data: products.map((item) => item.product),
        axisLabel: { interval: 0 },
      },
      yAxis: { type: 'value' as const, minInterval: 1 },
      series: types.map((type) => ({
        name: type,
        type: 'bar' as const,
        stack: 'total',
        barMaxWidth: 48,
        data: products.map((product) =>
          product.types.find((item) => item.type === type)?.count ?? 0
        ),
      })),
    }
  }, [data])

  /** 类型分布横向条形图 */
  const typeChart = useMemo(() => {
    if (!data) return null
    const totals = [...data.type_totals].reverse()
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 140, right: 30, top: 10, bottom: 24 },
      xAxis: { type: 'value' as const, minInterval: 1 },
      yAxis: {
        type: 'category' as const,
        data: totals.map((item) => item.type),
        axisLabel: { width: 130, overflow: 'truncate' as const },
      },
      series: [
        {
          name: '异常数量',
          type: 'bar' as const,
          barMaxWidth: 22,
          data: totals.map((item) => item.count),
          label: { show: true, position: 'right' as const },
        },
      ],
    }
  }, [data])

  const yearOptions = [
    { label: '全部年份', value: 0 },
    ...configuredYears.map((item) => ({ label: `${item.year}年`, value: item.year })),
  ]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 成品异常报告</p>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>成品异常报告总览</h1>
        <p style={{ marginTop: 8, color: 'var(--color-steel)' }}>
          由 AI 以资深现场 QA 视角，按产品与异常类型归类统计各年度成品异常记录；支持一键分析并实时同步飞书数据。
        </p>
      </div>

      {data && !data.ai_configured && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="AI 服务尚未配置"
          description="异常类型维度需要 AI 分析支持，请先在 系统管理 → AI 模型配置 中配置并启用 text 类型模型。"
        />
      )}

      <Space wrap style={{ marginBottom: 12 }}>
        <Select
          style={{ width: 130 }}
          value={yearFilter ?? 0}
          onChange={(value) => setYearFilter(value === 0 ? null : value)}
          options={yearOptions}
        />
        {configuredYears.length > 0 && configuredYears[0].feishu_url && (
          <Button
            icon={<LinkOutlined />}
            onClick={() =>
              window.open(
                configuredYears[configuredYears.length - 1].feishu_url as string,
                '_blank',
                'noopener,noreferrer',
              )
            }
          >
            打开飞书表格
          </Button>
        )}
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          loading={jobRunning}
          disabled={configuredYears.length === 0}
          onClick={() => void handleRunAnalysis()}
        >
          {jobRunning ? 'AI 分类中…' : data && data.unclassified > 0 ? `AI 分类（${data.unclassified} 条待分析）` : 'AI 分类'}
        </Button>
        <Button
          icon={<MessageOutlined />}
          disabled={configuredYears.length === 0}
          onClick={() => setChatOpen(true)}
        >
          AI 助手
        </Button>
      </Space>

      {jobRunning && statusQuery.data?.progress && (
        <Alert type="info" showIcon style={{ marginBottom: 12 }} message={statusQuery.data.progress} />
      )}

      <FinishedProductAnomalyChat
        open={chatOpen}
        year={yearFilter}
        onClose={() => setChatOpen(false)}
      />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic title="异常记录总数" value={data?.total ?? 0} suffix="条" />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic title="已完成 AI 分类" value={data?.analyzed ?? 0} suffix="条" />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic
              title="待分析"
              value={data?.unclassified ?? 0}
              suffix="条"
              styles={
                data && data.unclassified > 0 ? { content: { color: '#d46b08' } } : undefined
              }
            />
            {data?.last_analyzed_at && (
              <span style={{ color: 'var(--color-steel)', fontSize: 12 }}>
                最近分析：{dayjs(data.last_analyzed_at).format('YYYY-MM-DD HH:mm')}
              </span>
            )}
          </Card>
        </Col>
      </Row>

      <OpenAnomalyBoard data={data} onOpenLedger={(year) => void router.push(`/quality/anomaly-report/ledger?year=${year}`)} />

      {productChart && (
        <Card title="各产品异常数量（按异常类型堆叠）" size="small" style={{ marginBottom: 16 }}>
          <ReactECharts
            option={productChart}
            notMerge
            style={{ height: 380, width: '100%' }}
          />
        </Card>
      )}

      {typeChart && (
        <Card title="异常类型分布" size="small" style={{ marginBottom: 16 }}>
          <ReactECharts option={typeChart} notMerge style={{ height: 320, width: '100%' }} />
        </Card>
      )}

      {configuredYears.length > 0 && (
        <Card title="年度入口" size="small">
          <Space wrap>
            {configuredYears.map((status) => (
              <Button
                key={status.year}
                icon={<RightOutlined />}
                onClick={() => {
                  router.push(`/quality/anomaly-report/ledger?year=${status.year}`)
                }}
              >
                {status.year}年台账
              </Button>
            ))}
          </Space>
        </Card>
      )}
    </div>
  )
}

const openColumns = (
  onOpenLedger: (year: number) => void
): ColumnsType<AnomalyOpenRecord> => [
  { title: '年份', key: 'year', dataIndex: 'year', width: 70 },
  {
    title: '日期',
    key: 'date',
    dataIndex: 'date',
    width: 104,
    render: (value: string) => value || '—',
  },
  { title: '产品', key: 'product', dataIndex: 'product', width: 120, ellipsis: true },
  { title: '异常类型', key: 'anomaly_type', dataIndex: 'anomaly_type', width: 150, ellipsis: true },
  {
    title: '不合格描述',
    key: 'desc',
    ellipsis: true,
    render: (_, row) => (
      <Tooltip title={row.desc} placement="topLeft">
        <span>{row.desc || '（无描述）'}</span>
      </Tooltip>
    ),
  },
  {
    title: '操作',
    key: 'action',
    width: 80,
    render: (_, row) => (
      <Button size="small" type="link" onClick={() => onOpenLedger(row.year)}>
        去台账
      </Button>
    ),
  },
]

/** 未关闭异常看板：口径 = 无调查报告说明 且 未结案（有报告或已结案均不统计）；自带年份筛选。 */
function OpenAnomalyBoard({
  data,
  onOpenLedger,
}: {
  data?: AnomalyDashboardData
  onOpenLedger: (year: number) => void
}) {
  const [boardYear, setBoardYear] = useState<number>(0)
  if (!data) return null
  const rows =
    boardYear === 0
      ? data.open_recent
      : data.open_recent.filter((row) => row.year === boardYear)
  return (
    <Card
      title="未关闭异常看板"
      size="small"
      style={{ marginBottom: 16 }}
      extra={
        <Select
          size="small"
          style={{ width: 150 }}
          value={boardYear}
          onChange={setBoardYear}
          options={[
            { label: `全部（${data.open_count}）`, value: 0 },
            ...data.by_year_open.map((item) => ({
              label: `${item.year}年（${item.open_count}）`,
              value: item.year,
            })),
          ]}
        />
      }
    >
      <Table<AnomalyOpenRecord>
        rowKey={(row) => `${row.year}-${row.id}`}
        size="small"
        dataSource={rows}
        columns={openColumns(onOpenLedger)}
        tableLayout="fixed"
        scroll={{ x: 900 }}
        pagination={{ pageSize: 10, showSizeChanger: false, showTotal: (count) => `共 ${count} 条` }}
        locale={{ emptyText: '没有未关闭的异常记录' }}
      />
    </Card>
  )
}
