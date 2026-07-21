'use client'

import { useEffect, useState, useCallback } from 'react'
import {
  Table, Card, Row, Col, Statistic, Input, Select, DatePicker, Button, Space, Tag, App,
  Drawer, Descriptions, Progress, Divider, Spin, Alert, Badge,
} from 'antd'
import {
  FileTextOutlined, PlusOutlined, EyeOutlined, ReloadOutlined,
  RobotOutlined, ThunderboltOutlined, WarningOutlined, CheckCircleOutlined,
  ExperimentOutlined,
} from '@ant-design/icons'
import dayjs, { Dayjs } from 'dayjs'
import {
  RegulatoryDocument, SummaryStats, DocumentListParams,
  fetchSummary, fetchDocuments,
  fetchAIAnalysis, fetchAIBatchAnalysis,
  AIAnalysisResult, AIBatchAnalysisResult,
} from '@/lib/api/regulatory-tracker-client'
import { markDocumentRead } from '@/actions/regulatory-tracker'

const { Search } = Input
const { RangePicker } = DatePicker

const IMPACT_CONFIG = {
  high: { color: '#ff4d4f', label: '高', icon: <WarningOutlined /> },
  medium: { color: '#faad14', label: '中', icon: <ExperimentOutlined /> },
  low: { color: '#1890ff', label: '低', icon: <CheckCircleOutlined /> },
  none: { color: '#8c8c8c', label: '无', icon: <CheckCircleOutlined /> },
}

const URGENCY_CONFIG = {
  urgent: { color: '#ff4d4f', label: '紧急' },
  normal: { color: '#faad14', label: '正常' },
  long_term: { color: '#52c41a', label: '长期' },
}

export default function RegulatoryTrackerPage() {
  const { message } = App.useApp()
  const [summary, setSummary] = useState<SummaryStats | null>(null)
  const [documents, setDocuments] = useState<RegulatoryDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const [keyword, setKeyword] = useState('')
  const [classification, setClassification] = useState<string | undefined>(undefined)
  const [statusText, setStatusText] = useState<string | undefined>(undefined)
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [isNew, setIsNew] = useState<boolean | undefined>(undefined)

  const [singleAnalysisOpen, setSingleAnalysisOpen] = useState(false)
  const [batchAnalysisOpen, setBatchAnalysisOpen] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [singleResult, setSingleResult] = useState<AIAnalysisResult | null>(null)
  const [batchResult, setBatchResult] = useState<AIBatchAnalysisResult | null>(null)
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  const loadSummary = useCallback(async () => {
    try {
      const data = await fetchSummary()
      setSummary(data)
    } catch {
      message.error('加载统计数据失败')
    }
  }, [])

  const loadDocuments = useCallback(async () => {
    setLoading(true)
    try {
      const params: DocumentListParams = { page, pageSize }
      if (keyword) params.keyword = keyword
      if (classification) params.classification = classification
      if (statusText) params.statusText = statusText
      if (dateRange && dateRange[0] && dateRange[1]) {
        params.publishDateFrom = dateRange[0].format('YYYY-MM-DD')
        params.publishDateTo = dateRange[1].format('YYYY-MM-DD')
      }
      if (isNew !== undefined) params.isNew = isNew
      const data = await fetchDocuments(params)
      setDocuments(data.items)
      setTotal(data.total)
    } catch {
      message.error('加载文档列表失败')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, keyword, classification, statusText, dateRange, isNew])

  useEffect(() => { loadSummary() }, [loadSummary])
  useEffect(() => { loadDocuments() }, [loadDocuments])

  const handleViewOriginal = async (record: RegulatoryDocument) => {
    if (record.originalUrl) {
      window.open(record.originalUrl, '_blank')
      if (record.isNew) {
        try {
          await markDocumentRead(record.id)
          message.success('已标记为已读')
          loadDocuments()
          loadSummary()
        } catch {
          message.error('标记已读失败')
        }
      }
    }
  }

  const handleSingleAnalysis = async (doc: RegulatoryDocument) => {
    setAiLoading(true)
    setSingleResult(null)
    setSingleAnalysisOpen(true)
    try {
      const result = await fetchAIAnalysis(doc)
      setSingleResult(result)
    } catch {
      message.error('AI 分析失败')
      setSingleAnalysisOpen(false)
    } finally {
      setAiLoading(false)
    }
  }

  const handleBatchAnalysis = async () => {
    if (documents.length === 0) {
      message.warning('当前列表无数据，无法进行批量分析')
      return
    }
    setAiLoading(true)
    setBatchResult(null)
    setBatchAnalysisOpen(true)
    try {
      const result = await fetchAIBatchAnalysis(documents)
      setBatchResult(result)
    } catch {
      message.error('AI 批量分析失败')
      setBatchAnalysisOpen(false)
    } finally {
      setAiLoading(false)
    }
  }

  const handleReset = () => {
    setKeyword('')
    setClassification(undefined)
    setStatusText(undefined)
    setDateRange(null)
    setIsNew(undefined)
    setPage(1)
  }

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: '35%',
      render: (text: string, record: RegulatoryDocument) => (
        <div>
          <span className="font-medium">{text}</span>
          {record.isNew && <Tag color="red" className="ml-2">NEW</Tag>}
        </div>
      ),
    },
    {
      title: '分类',
      dataIndex: 'classification',
      key: 'classification',
      width: '10%',
      render: (text: string) => text || '-',
    },
    {
      title: '状态',
      dataIndex: 'statusText',
      key: 'statusText',
      width: '8%',
      render: (text: string) => text ? <Tag color="blue">{text}</Tag> : '-',
    },
    {
      title: '发布日期',
      dataIndex: 'publishDate',
      key: 'publishDate',
      width: '10%',
      render: (text: string) => text ? dayjs(text).format('YYYY-MM-DD') : '-',
    },
    {
      title: '首次发现',
      dataIndex: 'firstFoundAt',
      key: 'firstFoundAt',
      width: '11%',
      render: (text: string) => text ? dayjs(text).format('YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: '26%',
      render: (_: unknown, record: RegulatoryDocument) => (
        <Space>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleViewOriginal(record)}>
            原文
          </Button>
          <Button
            type="link"
            size="small"
            icon={<RobotOutlined />}
            onClick={() => handleSingleAnalysis(record)}
          >
            AI 分析
          </Button>
        </Space>
      ),
    },
  ]

  const ImpactBadge = ({ level }: { level: 'high' | 'medium' | 'low' | 'none' }) => {
    const cfg = IMPACT_CONFIG[level]
    return <Tag icon={cfg.icon} color={cfg.color}>{cfg.label}影响</Tag>
  }

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">法规跟踪</h1>
          <p className="text-[14px] text-[var(--color-steel)]">CDE 国内药品技术指导原则实时监控 · 化学原料药影响评估</p>
        </div>
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          onClick={handleBatchAnalysis}
          loading={aiLoading && batchAnalysisOpen}
        >
          批量 AI 分析
        </Button>
      </div>

      <Row gutter={[16, 16]} className="mb-6">
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title="法规总数" value={summary?.totalCount || 0} prefix={<FileTextOutlined />} styles={{ content: { color: '#1890ff' } }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title="今日新增" value={summary?.todayNewCount || 0} prefix={<PlusOutlined />} styles={{ content: { color: '#52c41a' } }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title="未读法规" value={summary?.unreadNewCount || 0} prefix={<EyeOutlined />} styles={{ content: { color: '#faad14' } }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="最近同步"
              value={summary?.lastSyncTime ? dayjs(summary.lastSyncTime).format('MM-DD HH:mm') : '暂无'}
              prefix={<ReloadOutlined />}
              styles={{ content: { color: '#722ed1', fontSize: '20px' } }}
            />
          </Card>
        </Col>
      </Row>

      <Card className="mb-6">
        <Row gutter={[16, 16]}>
          <Col xs={24} md={8}>
            <Search placeholder="搜索标题关键词" value={keyword} onChange={(e) => setKeyword(e.target.value)} onSearch={() => setPage(1)} allowClear />
          </Col>
          <Col xs={24} md={8}>
            <Select placeholder="选择分类" value={classification} onChange={(v) => { setClassification(v); setPage(1) }} allowClear style={{ width: '100%' }}
              options={[{ label: '化学药', value: '化学药' }, { label: '生物制品', value: '生物制品' }, { label: '中药', value: '中药' }]} />
          </Col>
          <Col xs={24} md={8}>
            <Select placeholder="选择状态" value={statusText} onChange={(v) => { setStatusText(v); setPage(1) }} allowClear style={{ width: '100%' }}
              options={[{ label: '颁布', value: '颁布' }, { label: '征求意见', value: '征求意见' }]} />
          </Col>
          <Col xs={24} md={8}>
            <RangePicker value={dateRange} onChange={(dates) => { setDateRange(dates as [Dayjs | null, Dayjs | null] | null); setPage(1) }} style={{ width: '100%' }} placeholder={['发布日期开始', '发布日期结束']} />
          </Col>
          <Col xs={24} md={8}>
            <Select placeholder="新增状态" value={isNew} onChange={(v) => { setIsNew(v); setPage(1) }} allowClear style={{ width: '100%' }}
              options={[{ label: '新增', value: true }, { label: '已读', value: false }]} />
          </Col>
          <Col xs={24} md={8}>
            <Space>
              <Button type="primary" onClick={() => setPage(1)}>搜索</Button>
              <Button onClick={handleReset}>重置</Button>
            </Space>
          </Col>
        </Row>
      </Card>

      <Card>
        <Table
          columns={columns}
          dataSource={documents}
          rowKey="id"
          loading={loading}
          rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys) }}
          pagination={{
            current: page, pageSize, total,
            showSizeChanger: true, showQuickJumper: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => { setPage(p); setPageSize(ps) },
          }}
        />
      </Card>

      <Drawer
        title={<div className="flex items-center gap-2"><RobotOutlined /><span>AI 影响评估</span></div>}
        placement="right"
        styles={{ wrapper: { width: 520 } }}
        open={singleAnalysisOpen}
        onClose={() => setSingleAnalysisOpen(false)}
      >
        {aiLoading && !singleResult ? (
          <div className="flex flex-col items-center justify-center py-20">
            <Spin size="large" />
            <p className="mt-4 text-gray-500">正在分析法规对化学原料药的影响...</p>
          </div>
        ) : singleResult ? (
          <div>
            <div className="text-center mb-6">
              <div className="text-lg font-semibold mb-2">{singleResult.documentTitle}</div>
              <ImpactBadge level={singleResult.impactLevel} />
              <Progress
                percent={singleResult.impactScore}
                strokeColor={IMPACT_CONFIG[singleResult.impactLevel].color}
                format={(p) => `${p}分`}
                size="small"
                className="mt-3"
              />
            </div>
            <Divider />
            <Descriptions column={1} bordered size="small" className="mb-4">
              <Descriptions.Item label="影响摘要">{singleResult.impactSummary}</Descriptions.Item>
              <Descriptions.Item label="时效要求">
                <Tag color={URGENCY_CONFIG[singleResult.timelineUrgency].color}>
                  {URGENCY_CONFIG[singleResult.timelineUrgency].label}
                </Tag>
              </Descriptions.Item>
            </Descriptions>
            {singleResult.keyChanges.length > 0 && (
              <div className="mb-4">
                <h4 className="font-semibold mb-2"><ThunderboltOutlined className="mr-1" /> 关键变更点</h4>
                <ul className="space-y-1">
                  {singleResult.keyChanges.map((item) => (
                    <li key={item} className="py-1 flex items-start gap-2"><span className="text-blue-600">•</span>{item}</li>
                  ))}
                </ul>
              </div>
            )}
            {singleResult.impactAreas.length > 0 && (
              <div className="mb-4">
                <h4 className="font-semibold mb-2"><ExperimentOutlined className="mr-1" /> 影响领域</h4>
                <div className="flex flex-wrap gap-2">
                  {singleResult.impactAreas.map((area) => <Tag key={area} color="orange">{area}</Tag>)}
                </div>
              </div>
            )}
            {singleResult.complianceSuggestions.length > 0 && (
              <div className="mb-4">
                <h4 className="font-semibold mb-2"><WarningOutlined className="mr-1" /> 合规建议</h4>
                <ul className="space-y-1">
                  {singleResult.complianceSuggestions.map((item, idx) => (
                    <li key={idx} className="py-1 flex items-start gap-2"><Badge count={idx + 1} style={{ backgroundColor: '#1890ff' }} />{item}</li>
                  ))}
                </ul>
              </div>
            )}
            <Divider />
            <div className="text-xs text-gray-400 text-center">
              分析时间：{dayjs(singleResult.generatedAt).format('YYYY-MM-DD HH:mm:ss')}
            </div>
          </div>
        ) : null}
      </Drawer>

      <Drawer
        title={<div className="flex items-center gap-2"><ThunderboltOutlined /><span>批量影响评估报告</span></div>}
        placement="right"
        styles={{ wrapper: { width: 600 } }}
        open={batchAnalysisOpen}
        onClose={() => { setBatchAnalysisOpen(false); setBatchResult(null) }}
      >
        {aiLoading && !batchResult ? (
          <div className="flex flex-col items-center justify-center py-20">
            <Spin size="large" />
            <p className="mt-4 text-gray-500">正在批量分析 {documents.length} 条法规对化学原料药的影响...</p>
          </div>
        ) : batchResult ? (
          <div>
            <Alert
              type={batchResult.highImpact > 0 ? 'warning' : batchResult.mediumImpact > 0 ? 'info' : 'success'}
              title="总体评估"
              description={batchResult.overallAssessment}
              showIcon
              className="mb-6"
            />
            <div className="mb-6">
              <h4 className="font-semibold mb-3">影响等级分布</h4>
              <Row gutter={16}>
                <Col span={6}><Card size="small" className="text-center"><Statistic title="高影响" value={batchResult.highImpact} styles={{ content: { color: '#ff4d4f' } }} /></Card></Col>
                <Col span={6}><Card size="small" className="text-center"><Statistic title="中影响" value={batchResult.mediumImpact} styles={{ content: { color: '#faad14' } }} /></Card></Col>
                <Col span={6}><Card size="small" className="text-center"><Statistic title="低影响" value={batchResult.lowImpact} styles={{ content: { color: '#1890ff' } }} /></Card></Col>
                <Col span={6}><Card size="small" className="text-center"><Statistic title="无影响" value={batchResult.noneImpact} styles={{ content: { color: '#8c8c8c' } }} /></Card></Col>
              </Row>
            </div>
            <Divider />
            <div>
              <h4 className="font-semibold mb-3"><WarningOutlined className="mr-1 text-red-500" /> 重点关注法规（按影响程度排序）</h4>
              {batchResult.topConcerns.length > 0 ? (
                <div className="space-y-3">
                  {batchResult.topConcerns.map((item) => (
                    <div key={item.documentId} className="flex items-start gap-3 p-3 border border-gray-200 rounded-md">
                      <ImpactBadge level={item.impactLevel} />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium mb-1">{item.title}</div>
                        <div className="text-sm text-gray-500">{item.reason}</div>
                      </div>
                      <Button
                        type="link"
                        size="small"
                        icon={<RobotOutlined />}
                        onClick={() => {
                          const doc = documents.find(d => d.id === item.documentId)
                          if (doc) { setBatchAnalysisOpen(false); handleSingleAnalysis(doc) }
                        }}
                      >详情</Button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center text-gray-400 py-4">当前列表无需重点关注的法规</div>
              )}
            </div>
            <Divider />
            <div className="text-xs text-gray-400 text-center">
              分析数量：{batchResult.totalAnalyzed} 条 · 分析时间：{dayjs(batchResult.generatedAt).format('YYYY-MM-DD HH:mm:ss')}
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  )
}
