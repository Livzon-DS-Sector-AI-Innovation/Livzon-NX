'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Col,
  Drawer,
  Input,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileAddOutlined,
  FundOutlined,
  RadiusSettingOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import {
  getOhDetectionReports,
  getOhDetectionResults,
  deleteOhDetectionReport,
} from '@/actions/safety'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import OhDetectionImportModal from './OhDetectionImportModal'
import {
  OH_DETECTION_FACTOR_CATEGORY_OPTIONS,
  OH_DETECTION_RECORD_TYPE_OPTIONS,
  OH_DETECTION_VERDICT_OPTIONS,
  type OhDetectionReport,
  type OhDetectionResult,
} from '@/types/safety'

const { Text } = Typography

const PAGE_KEY = 'safety:occupational-health-group:oh-monitor'
const PAGE_SIZE = 20

const CATEGORY_LABELS: Record<string, string> = Object.fromEntries(
  OH_DETECTION_FACTOR_CATEGORY_OPTIONS.map((o) => [o.value, o.label])
)
const RECORD_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  OH_DETECTION_RECORD_TYPE_OPTIONS.map((o) => [o.value, o.label])
)
const VERDICT_TAGS: Record<string, { label: string; color: string }> =
  Object.fromEntries(OH_DETECTION_VERDICT_OPTIONS.map((o) => [o.value, { label: o.label, color: o.color }]))
const MODE_TAGS: Record<string, { label: string; color: string }> = {
  rules: { label: '规则识别', color: 'blue' },
  llm: { label: 'AI 识别', color: 'purple' },
  mixed: { label: '规则 + AI', color: 'geekblue' },
}

export default function OhDetectionReportPanel() {
  const { message } = App.useApp()
  const perms = usePagePermissions(PAGE_KEY)

  const [reports, setReports] = useState<OhDetectionReport[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [keyword, setKeyword] = useState<string | undefined>(undefined)
  const [stats, setStats] = useState({ report_count: 0, total_points: 0, exceed_points: 0, noise_post_points: 0 })
  const [importOpen, setImportOpen] = useState(false)

  const [drawerReport, setDrawerReport] = useState<OhDetectionReport | null>(null)
  const [results, setResults] = useState<OhDetectionResult[]>([])
  const [resultsLoading, setResultsLoading] = useState(false)
  const [resultsTotal, setResultsTotal] = useState(0)
  const [resultFilters, setResultFilters] = useState<{
    factor_category?: string
    record_type?: string
    verdict?: string
    is_noise_post?: boolean
    keyword?: string
  }>({})
  const [resultPage, setResultPage] = useState(1)

  const loadReports = useCallback(async () => {
    const res = await getOhDetectionReports({ page: 1, page_size: 100, keyword })
    setError(null)
    setLoading(false)
    if (res.code !== 200) {
      setError(res.message || '加载检测报告失败')
      return
    }
    setReports(res.data || [])
    if (res.meta) {
      setStats({
        report_count: res.meta.report_count ?? (res.data || []).length,
        total_points: res.meta.total_points ?? 0,
        exceed_points: res.meta.exceed_points ?? 0,
        noise_post_points: res.meta.noise_post_points ?? 0,
      })
    }
  }, [keyword])

  useEffect(() => {
    // 数据加载放入宏任务回调，规避 react-hooks/set-state-in-effect
    const timer = setTimeout(() => void loadReports(), 0)
    return () => clearTimeout(timer)
  }, [loadReports])

  const loadResults = useCallback(
    async (reportId: string, page: number) => {
      const res = await getOhDetectionResults(reportId, {
        page,
        page_size: PAGE_SIZE,
        ...resultFilters,
      })
      setResultsLoading(false)
      if (res.code !== 200) {
        message.error(res.message || '加载检测明细失败')
        return
      }
      setResults(res.data || [])
      setResultsTotal(res.meta?.total ?? res.data?.length ?? 0)
    },
    [resultFilters, message]
  )

  const openDetail = useCallback((report: OhDetectionReport) => {
    setDrawerReport(report)
    setResultPage(1)
    setResultFilters({})
    setResultsLoading(true)
  }, [])

  useEffect(() => {
    if (!drawerReport) return
    // 同上：明细加载放入宏任务回调
    const timer = setTimeout(() => void loadResults(drawerReport.id, resultPage), 0)
    return () => clearTimeout(timer)
  }, [drawerReport, resultPage, loadResults])

  const handleDelete = useCallback(
    async (id: string) => {
      const res = await deleteOhDetectionReport(id)
      if (res.code !== 200) {
        message.error(res.message || '删除失败')
        return
      }
      message.success('已删除')
      void loadReports()
    },
    [loadReports, message]
  )

  const handleDownload = useCallback(
    async (report: OhDetectionReport) => {
      const res = await fetch(`/api/v1/safety/oh-detection-reports/${report.id}/file`, {
        headers: { 'X-Dazah-Page-Key': PAGE_KEY },
      })
      if (!res.ok) {
        message.error('下载失败：原始报告文件不存在')
        return
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = report.source_file_name || `${report.report_no}.pdf`
      anchor.click()
      URL.revokeObjectURL(url)
    },
    [message]
  )

  const reportColumns = [
    {
      title: '报告编号',
      dataIndex: 'report_no',
      key: 'report_no',
      width: 160,
      render: (value: string, record: OhDetectionReport) => (
        <Button type="link" size="small" style={{ padding: 0 }} onClick={() => openDetail(record)}>
          {value}
        </Button>
      ),
    },
    { title: '受检企业', dataIndex: 'company_name', key: 'company_name', width: 180, ellipsis: true },
    { title: '检测机构', dataIndex: 'detection_agency', key: 'detection_agency', width: 180, ellipsis: true },
    {
      title: '检测日期',
      dataIndex: 'detection_date',
      key: 'detection_date',
      width: 110,
      render: (value?: string | null) => value || '-',
    },
    { title: '表格', dataIndex: 'table_count', key: 'table_count', width: 70, align: 'center' as const },
    { title: '检测记录', dataIndex: 'total_points', key: 'total_points', width: 90, align: 'center' as const },
    {
      title: '超标',
      dataIndex: 'exceed_points',
      key: 'exceed_points',
      width: 70,
      align: 'center' as const,
      render: (value: number) => (
        <Text type={value > 0 ? 'danger' : undefined}>{value}</Text>
      ),
    },
    {
      title: '噪声作业岗位',
      dataIndex: 'noise_post_points',
      key: 'noise_post_points',
      width: 110,
      align: 'center' as const,
    },
    {
      title: '识别方式',
      dataIndex: 'parse_mode',
      key: 'parse_mode',
      width: 100,
      render: (value: string) => (
        <Tag color={MODE_TAGS[value]?.color}>{MODE_TAGS[value]?.label ?? value}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: unknown, record: OhDetectionReport) => (
        <Space size={0} wrap>
          <Tooltip title="明细">
            <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => openDetail(record)} />
          </Tooltip>
          <Tooltip title="下载原报告">
            <Button
              type="link"
              size="small"
              icon={<DownloadOutlined />}
              onClick={() => void handleDownload(record)}
            />
          </Tooltip>
          {perms.canDelete && (
            <Popconfirm title="确认删除该检测报告及其明细？" onConfirm={() => void handleDelete(record.id)}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const resultColumns = [
    { title: '#', dataIndex: 'seq', key: 'seq', width: 55 },
    { title: '表号', dataIndex: 'table_ref', key: 'table_ref', width: 80 },
    {
      title: '危害因素',
      key: 'factor',
      width: 150,
      render: (_: unknown, record: OhDetectionResult) => (
        <Space size={4} wrap>
          <Text>{record.factor_name}</Text>
          <Tag style={{ marginInlineEnd: 0 }}>{CATEGORY_LABELS[record.factor_category] ?? record.factor_category}</Tag>
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'record_type',
      key: 'record_type',
      width: 100,
      render: (value: string) => RECORD_TYPE_LABELS[value] ?? value,
    },
    { title: '车间', dataIndex: 'workshop', key: 'workshop', width: 110, ellipsis: true },
    { title: '岗位', dataIndex: 'post', key: 'post', width: 90, ellipsis: true },
    { title: '采样点/测量地点', dataIndex: 'sample_point', key: 'sample_point', width: 150, ellipsis: true },
    {
      title: '检测值',
      key: 'measured',
      width: 110,
      render: (_: unknown, record: OhDetectionResult) => (
        <span>
          {record.measured_value}
          {record.unit ? ` ${record.unit}` : ''}
        </span>
      ),
    },
    {
      title: '限值',
      key: 'limit',
      width: 120,
      render: (_: unknown, record: OhDetectionResult) =>
        record.limit_type === 'none' || record.limit_value_num == null
          ? '-'
          : `${record.limit_type} ${record.limit_value_num}`,
    },
    {
      title: '判定',
      key: 'verdict',
      width: 150,
      render: (_: unknown, record: OhDetectionResult) => (
        <Space size={4} wrap>
          <Tag color={VERDICT_TAGS[record.verdict]?.color}>
            {VERDICT_TAGS[record.verdict]?.label ?? record.verdict}
          </Tag>
          {record.is_noise_post && <Tag color="orange">噪声作业岗位</Tag>}
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <Row gutter={12}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="报告数" value={stats.report_count} prefix={<FileAddOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="检测记录" value={stats.total_points} prefix={<FundOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="超标记录"
              value={stats.exceed_points}
              prefix={<WarningOutlined />}
              valueStyle={stats.exceed_points > 0 ? { color: '#cf1322' } : undefined}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="噪声作业岗位记录"
              value={stats.noise_post_points}
              prefix={<RadiusSettingOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Space wrap style={{ marginBottom: 0 }}>
        <Input.Search
          allowClear
          placeholder="搜索报告编号/企业/机构"
          style={{ width: 260 }}
          onSearch={(v) => {
            setLoading(true)
            setKeyword(v || undefined)
          }}
        />
        <Button
          type="primary"
          icon={<FileAddOutlined />}
          disabled={!perms.canOperate || !perms.canImport}
          onClick={() => setImportOpen(true)}
        >
          导入检测报告
        </Button>
        {!perms.canOperate && <Text type="secondary">当前页面无操作权限，导入不可用</Text>}
      </Space>

      <Table
        size="small"
        rowKey="id"
        loading={loading}
        columns={reportColumns}
        dataSource={reports}
        scroll={{ x: 1300 }}
        pagination={{ pageSize: PAGE_SIZE, showSizeChanger: false, showTotal: (t) => `共 ${t} 份` }}
        locale={{ emptyText: error ? `加载失败：${error}` : '暂无检测报告，点击「导入检测报告」上传 PDF 自动识别' }}
      />

      <OhDetectionImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => void loadReports()}
      />

      <Drawer
        title={
          drawerReport
            ? `检测明细 — ${drawerReport.report_no}`
            : '检测明细'
        }
        placement="right"
        styles={{ wrapper: { width: 1080 } }}
        open={!!drawerReport}
        onClose={() => setDrawerReport(null)}
        destroyOnHidden
      >
        <Space wrap style={{ marginBottom: 12 }}>
          <Select
            allowClear
            placeholder="危害因素类别"
            style={{ width: 140 }}
            options={OH_DETECTION_FACTOR_CATEGORY_OPTIONS}
            value={resultFilters.factor_category}
            onChange={(v) => {
              setResultPage(1)
              setResultFilters((f) => ({ ...f, factor_category: v }))
              setResultsLoading(true)
            }}
          />
          <Select
            allowClear
            placeholder="记录类型"
            style={{ width: 130 }}
            options={OH_DETECTION_RECORD_TYPE_OPTIONS}
            value={resultFilters.record_type}
            onChange={(v) => {
              setResultPage(1)
              setResultFilters((f) => ({ ...f, record_type: v }))
              setResultsLoading(true)
            }}
          />
          <Select
            allowClear
            placeholder="判定结果"
            style={{ width: 110 }}
            options={OH_DETECTION_VERDICT_OPTIONS}
            value={resultFilters.verdict}
            onChange={(v) => {
              setResultPage(1)
              setResultFilters((f) => ({ ...f, verdict: v }))
              setResultsLoading(true)
            }}
          />
          <Select
            allowClear
            placeholder="噪声作业岗位"
            style={{ width: 140 }}
            options={[
              { value: 'true', label: '是' },
              { value: 'false', label: '否' },
            ]}
            value={resultFilters.is_noise_post === undefined ? undefined : String(resultFilters.is_noise_post)}
            onChange={(v) => {
              setResultPage(1)
              setResultFilters((f) => ({
                ...f,
                is_noise_post: v === undefined || v === null ? undefined : v === 'true',
              }))
              setResultsLoading(true)
            }}
          />
          <Input.Search
            allowClear
            placeholder="搜索因素/车间/岗位/点位"
            style={{ width: 220 }}
            onSearch={(v) => {
              setResultPage(1)
              setResultFilters((f) => ({ ...f, keyword: v || undefined }))
              setResultsLoading(true)
            }}
          />
        </Space>
        <Table
          size="small"
          rowKey="id"
          loading={resultsLoading}
          columns={resultColumns}
          dataSource={results}
          scroll={{ x: 1100 }}
          pagination={{
            current: resultPage,
            pageSize: PAGE_SIZE,
            total: resultsTotal,
            showSizeChanger: false,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (page) => setResultPage(page),
          }}
        />
      </Drawer>
    </div>
  )
}
