'use client'

import { useEffect, useState, useCallback } from 'react'
import {
  App,
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Input,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
} from 'antd'
import {
  AlertOutlined,
  BarChartOutlined,
  MessageOutlined,
  WarningOutlined,
  FileTextOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import {
  fetchWarehouseHardwareCostAnomalies,
  fetchWarehouseHardwareCostSummary,
  fetchWarehouseTrendAnomalies,
  fetchWarehouseTrendProductLines,
  fetchWarehouseTrendSummary,
} from '@/lib/api/client/warehouse'
import { chatWarehouseAiAction } from '@/actions/warehouse'
import type {
  WarehouseHardwareCostAnomalyItem,
  WarehouseHardwareCostSummary,
  WarehouseTrendAnomalyItem,
  WarehouseTrendProductLineItem,
  WarehouseTrendSummary,
} from '@/types/warehouse'

const { Title, Text, Paragraph } = Typography

interface AnomalyItem {
  anomaly_type: string
  severity: string
  material_name: string
  material_type: string
  details: Record<string, unknown>
  suggestion: string
  detected_at: string
}

interface InventorySummary {
  raw_materials: {
    total: number
    low_stock: number
    zero_stock: number
    warning: number
  }
  packaging_materials: {
    total: number
    low_stock: number
    zero_stock: number
    warning: number
  }
  products: {
    total: number
    with_stock: number
  }
  summary: {
    total_items: number
    anomaly_count: number
  }
}

interface AnalysisReport {
  overall_status: string
  risk_level: string
  key_issues: string[]
  recommendations: string[]
  summary_text: string
}

const SEVERITY_COLORS: Record<string, string> = {
  high: 'error',
  medium: 'warning',
  low: 'default',
}

const SEVERITY_LABELS: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
}

const ANOMALY_TYPE_LABELS: Record<string, string> = {
  stock_zero: '库存为零',
  stock_low: '库存不足',
  warning_status: '预警状态',
  product_backlog: '成品积压',
  unusual_outbound: '异常出库',
}

const MATERIAL_TYPE_LABELS: Record<string, string> = {
  raw: '原辅料',
  packaging: '包材',
  product: '成品',
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

function normalizeInventorySummary(value: unknown): InventorySummary {
  const source = value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
  const section = (key: string) => {
    const value = source[key]
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown>
      : {}
  }
  const raw = section('raw_materials')
  const packaging = section('packaging_materials')
  const products = section('products')
  const overall = section('summary')
  const numberValue = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value : Number(value || 0)
  return {
    raw_materials: {
      total: numberValue(raw.total),
      low_stock: numberValue(raw.low_stock),
      zero_stock: numberValue(raw.zero_stock),
      warning: numberValue(raw.warning),
    },
    packaging_materials: {
      total: numberValue(packaging.total),
      low_stock: numberValue(packaging.low_stock),
      zero_stock: numberValue(packaging.zero_stock),
      warning: numberValue(packaging.warning),
    },
    products: {
      total: numberValue(products.total),
      with_stock: numberValue(products.with_stock),
    },
    summary: {
      total_items: numberValue(overall.total_items),
      anomaly_count: numberValue(overall.anomaly_count),
    },
  }
}

function getTrendDeltaText(value: number | null): string {
  if (value === null) {
    return '新增消耗'
  }
  const sign = value > 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(1)}%`
}

function getRiskLabel(level: WarehouseTrendAnomalyItem['risk_level']): string {
  if (level === 'high') return '高风险'
  if (level === 'medium') return '中风险'
  return '低风险'
}

export function WarehouseAiPanel() {
  const { message } = App.useApp()
  const [anomalies, setAnomalies] = useState<AnomalyItem[]>([])
  const [summary, setSummary] = useState<InventorySummary | null>(null)
  const [report, setReport] = useState<AnalysisReport | null>(null)
  const [trendSummary, setTrendSummary] = useState<WarehouseTrendSummary | null>(null)
  const [trendAnomalies, setTrendAnomalies] = useState<WarehouseTrendAnomalyItem[]>([])
  const [trendProductLines, setTrendProductLines] = useState<WarehouseTrendProductLineItem[]>([])
  const [hardwareCostAnomalies, setHardwareCostAnomalies] = useState<WarehouseHardwareCostAnomalyItem[]>([])
  const [hardwareCostSummary, setHardwareCostSummary] = useState<WarehouseHardwareCostSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [reportLoading, setReportLoading] = useState(false)
  const [chatLoading, setChatLoading] = useState(false)
  const [chatQuestion, setChatQuestion] = useState('')
  const [chatResponse, setChatResponse] = useState('')
  const [activeTab, setActiveTab] = useState<'anomalies' | 'chat' | 'report'>('anomalies')

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const [anomaliesResult, summaryResult, trendSummaryResult, trendAnomaliesResult, trendProductLinesResult, hardwareCostAnomaliesResult, hardwareCostSummaryResult] =
        await Promise.allSettled([
          fetch('/api/v1/warehouse/ai/anomalies').then((res) => res.json()),
          fetch('/api/v1/warehouse/ai/summary').then((res) => res.json()),
          fetchWarehouseTrendSummary(),
          fetchWarehouseTrendAnomalies(),
          fetchWarehouseTrendProductLines(),
          fetchWarehouseHardwareCostAnomalies(),
          fetchWarehouseHardwareCostSummary(),
        ])

      if (anomaliesResult.status === 'fulfilled') {
        setAnomalies(anomaliesResult.value.data || [])
      } else {
        setAnomalies([])
      }

      if (summaryResult.status === 'fulfilled') {
        setSummary(normalizeInventorySummary(summaryResult.value.data))
      } else {
        setSummary(null)
      }

      if (trendSummaryResult.status === 'fulfilled') {
        setTrendSummary(trendSummaryResult.value)
      } else {
        setTrendSummary(null)
      }

      if (trendAnomaliesResult.status === 'fulfilled') {
        setTrendAnomalies(trendAnomaliesResult.value)
      } else {
        setTrendAnomalies([])
      }

      if (trendProductLinesResult.status === 'fulfilled') {
        setTrendProductLines(trendProductLinesResult.value)
      } else {
        setTrendProductLines([])
      }

      if (hardwareCostAnomaliesResult.status === 'fulfilled') {
        setHardwareCostAnomalies(hardwareCostAnomaliesResult.value)
      } else {
        setHardwareCostAnomalies([])
      }

      if (hardwareCostSummaryResult.status === 'fulfilled') {
        setHardwareCostSummary(hardwareCostSummaryResult.value)
      } else {
        setHardwareCostSummary(null)
      }
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '数据加载失败'))
    } finally {
      setLoading(false)
    }
  }, [message])

  const fetchReport = useCallback(async () => {
    setReportLoading(true)
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 120000)
    try {
      const res = await fetch('/api/v1/warehouse/ai/report', {
        signal: controller.signal,
      })
      if (res.ok) {
        const data = await res.json()
        setReport(data.data)
      } else {
        message.error('报告生成失败')
      }
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        message.error('报告生成超时，请稍后重试')
      } else {
        message.error(getErrorMessage(error, '报告生成失败'))
      }
    } finally {
      clearTimeout(timeoutId)
      setReportLoading(false)
    }
  }, [message])

  const handleChat = useCallback(async () => {
    if (!chatQuestion.trim()) {
      message.warning('请输入问题')
      return
    }

    setChatLoading(true)
    setChatResponse('')
    try {
      const data = await chatWarehouseAiAction(chatQuestion)
      setChatResponse(data.response || '暂无回复')
    } catch (error: unknown) {
      message.error(getErrorMessage(error, 'AI回复失败'))
    } finally {
      setChatLoading(false)
    }
  }, [chatQuestion, message])

  useEffect(() => {
    const loadData = async () => {
      await fetchData()
    }
    void loadData()
  }, [fetchData])

  const renderAnomalies = () => (
    <div>
      <Space className="mb-4">
        <Button
          type="primary"
          icon={<ReloadOutlined />}
          onClick={fetchData}
          loading={loading}
        >
          刷新检测
        </Button>
        <Text type="secondary">
          检测时间：{anomalies[0]?.detected_at || '暂无'}
        </Text>
      </Space>

      {trendSummary && (
        <Row gutter={16} className="mb-4">
          <Col span={6}>
            <Card>
              <Statistic title="趋势异常物料" value={trendSummary.total} />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="高风险物料"
                value={trendSummary.high_risk}
                styles={{
                  content: {
                    color: trendSummary.high_risk > 0 ? '#cf1322' : undefined,
                  },
                }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic title="原辅料异常" value={trendSummary.raw_count} />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic title="包材异常" value={trendSummary.packaging_count} />
            </Card>
          </Col>
        </Row>
      )}

      <Card className="mb-4" title="产品线趋势概览">
        {trendProductLines.length === 0 ? (
          <Empty description="暂无产品线趋势数据" />
        ) : (
          <div className="space-y-3">
            {trendProductLines.slice(0, 6).map((item) => (
              <div
                key={item.product_line || '未分类'}
                className="flex items-center justify-between gap-4 border-b border-[var(--color-border)] pb-3 last:border-b-0"
              >
                <div>
                  <Text strong>{item.product_line || '未分类'}</Text>
                  <div className="text-[12px] text-[var(--color-text-secondary)]">
                    本周 {item.current_week_usage} / 历史周均 {item.history_week_avg_usage} / 偏差{' '}
                    {getTrendDeltaText(item.usage_delta_ratio)}
                  </div>
                </div>
                <Tag color={item.high_risk_count > 0 ? 'error' : item.medium_risk_count > 0 ? 'warning' : 'default'}>
                  高风险 {item.high_risk_count} / 中风险 {item.medium_risk_count}
                </Tag>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className="mb-4" title="异常物料明细">
        {trendAnomalies.length === 0 ? (
          <Empty description="暂无趋势异常物料" />
        ) : (
          <div className="space-y-3">
            {trendAnomalies.slice(0, 20).map((item) => (
              <Card key={`${item.material_type}-${item.material_name}`} size="small">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <Space wrap>
                      <Text strong>{item.material_name}</Text>
                      <Tag>{MATERIAL_TYPE_LABELS[item.material_type]}</Tag>
                      <Tag color={SEVERITY_COLORS[item.risk_level]}>{getRiskLabel(item.risk_level)}</Tag>
                    </Space>
                    <div className="mt-2 text-[13px] text-[var(--color-text-secondary)]">
                      产品线：{item.product_line || '未分类'} | 本周：{item.current_week_usage} | 周均：
                      {item.history_week_avg_usage}
                    </div>
                    <div className="text-[13px] text-[var(--color-text-secondary)]">
                      当前库存：{item.current_inventory} | 安全库存：{item.safety_inventory} | 可支撑天数：
                      {item.estimated_cover_days ?? '-'}
                    </div>
                    <div className="mt-2 text-[13px]">{item.reason}</div>
                    <div className="mt-1 text-[13px] text-[var(--color-text-secondary)]">
                      {item.suggestion}
                    </div>
                  </div>
                  <Text strong>{getTrendDeltaText(item.usage_delta_ratio)}</Text>
                </div>
              </Card>
            ))}
          </div>
        )}
      </Card>

      {hardwareCostSummary && (
        <Row gutter={16} className="mb-4">
          <Col span={6}>
            <Card>
              <Statistic
                title="五金费用异常车间"
                value={hardwareCostSummary.anomaly_workshops}
                styles={{
                  content: {
                    color: hardwareCostSummary.anomaly_workshops > 0 ? '#cf1322' : undefined,
                  },
                }}
              />
            </Card>
          </Col>
        </Row>
      )}

      <Card className="mb-4" title="五金费用异常车间">
        {hardwareCostAnomalies.length === 0 ? (
          <Empty description="暂无五金费用异常车间" />
        ) : (
          <div className="space-y-3">
            {hardwareCostAnomalies.slice(0, 10).map((item) => (
              <Card key={item.workshop_name} size="small">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <Space wrap>
                      <Text strong>{item.workshop_name}</Text>
                      <Tag color={item.risk_level === 'high' ? 'error' : 'warning'}>
                        {item.risk_level === 'high' ? '高风险' : '中风险'}
                      </Tag>
                    </Space>
                    <div className="mt-2 text-[13px] text-[var(--color-text-secondary)]">
                      本月：{item.current_month_cost.toFixed(2)} 元 | 月均：{item.history_month_avg_cost.toFixed(2)} 元
                    </div>
                    <div className="mt-2 text-[13px]">{item.reason}</div>
                    <div className="mt-1 text-[13px] text-[var(--color-text-secondary)]">
                      {item.suggestion}
                    </div>
                  </div>
                  <Text strong>
                    {item.cost_delta_ratio !== null ? `+${(item.cost_delta_ratio * 100).toFixed(1)}%` : '-'}
                  </Text>
                </div>
              </Card>
            ))}
          </div>
        )}
      </Card>

      {anomalies.length === 0 ? (
        <Empty description="暂无异常检测结果" />
      ) : (
        <div className="space-y-3">
          {anomalies.map((item) => (
            <div key={`${item.material_type}-${item.material_name}-${item.anomaly_type}`}>
              <Card
                className="w-full"
                size="small"
                title={
                  <Space>
                    <Badge status={SEVERITY_COLORS[item.severity] as 'error' | 'warning' | 'default'} />
                    <Text strong>{item.material_name}</Text>
                    <Tag>{MATERIAL_TYPE_LABELS[item.material_type] || item.material_type}</Tag>
                  </Space>
                }
                extra={
                  <Tag color={SEVERITY_COLORS[item.severity]}>
                    {SEVERITY_LABELS[item.severity]}风险
                  </Tag>
                }
              >
                <div className="flex flex-col gap-2">
                  <Text>
                    <AlertOutlined className="mr-2" />
                    异常类型：{ANOMALY_TYPE_LABELS[item.anomaly_type] || item.anomaly_type}
                  </Text>
                  <Text type="secondary">{item.suggestion}</Text>
                  {item.details && Object.keys(item.details).length > 0 && (
                    <div className="mt-2">
                      <Text type="secondary" className="text-xs">
                        详情：{JSON.stringify(item.details)}
                      </Text>
                    </div>
                  )}
                </div>
              </Card>
            </div>
          ))}
        </div>
      )}
    </div>
  )

  const renderChat = () => (
    <div>
      <Space.Compact className="w-full mb-4">
        <Input
          placeholder="输入关于仓储趋势的问题，如：哪些原辅料本周用量异常上升？"
          value={chatQuestion}
          onChange={(e) => setChatQuestion(e.target.value)}
          onPressEnter={handleChat}
          size="large"
        />
        <Button
          type="primary"
          size="large"
          onClick={handleChat}
          loading={chatLoading}
        >
          提问
        </Button>
      </Space.Compact>

      {chatResponse && (
        <Card className="mt-4">
          <Title level={5}>AI回复</Title>
          <Paragraph>{chatResponse}</Paragraph>
        </Card>
      )}

      <Card className="mt-4" title="常见问题示例">
        <div className="flex flex-col gap-2">
          {[
            '上月哪些车间五金领用费用异常偏高？',
            '本月五金费用最高的车间是哪个？',
            '最近7天哪些原辅料用量异常上升？',
            '当前哪些包材库存不足？',
            '现在成品库存情况怎么样？',
            '请总结当前仓储最需要关注的问题',
            '哪条产品线本周物料波动最大？',
            '哪些高消耗物料可能在一周内断料？',
          ].map((q) => (
            <Button
              key={q}
              type="text"
              onClick={() => setChatQuestion(q)}
              className="text-left"
            >
              {q}
            </Button>
          ))}
        </div>
      </Card>
    </div>
  )

  const renderReport = () => (
    <div>
      <Space className="mb-4">
        <Button
          type="primary"
          icon={<FileTextOutlined />}
          onClick={fetchReport}
          loading={reportLoading}
        >
          生成报告
        </Button>
      </Space>

      {report ? (
        <Card>
          <div className="flex flex-col gap-6">
            <div>
              <Text strong>总体状况：</Text>
              <Tag
                color={
                  report.overall_status === '正常'
                    ? 'success'
                    : report.overall_status === '需关注'
                    ? 'warning'
                    : 'error'
                }
              >
                {report.overall_status}
              </Tag>
              <Text strong className="ml-4">风险等级：</Text>
              <Tag
                color={
                  report.risk_level === '低'
                    ? 'success'
                    : report.risk_level === '中'
                    ? 'warning'
                    : 'error'
                }
              >
                {report.risk_level}
              </Tag>
            </div>

            <Paragraph>{report.summary_text}</Paragraph>

            {report.key_issues.length > 0 && (
              <div>
                <Title level={5}>关键问题</Title>
                <div className="flex flex-col gap-2">
                  {report.key_issues.map((issue) => (
                    <div key={issue} className="flex items-start gap-2">
                      <WarningOutlined className="mt-1 text-orange-500" />
                      <span>{issue}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {report.recommendations.length > 0 && (
              <div>
                <Title level={5}>改进建议</Title>
                <div className="flex flex-col gap-2">
                  {report.recommendations.map((rec) => (
                    <div key={rec} className="flex items-start gap-2">
                      <BarChartOutlined className="mt-1 text-blue-500" />
                      <span>{rec}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Card>
      ) : (
        <Empty description="点击生成报告按钮获取AI分析报告" />
      )}
    </div>
  )

  return (
    <div className="w-full">
      <Title level={3} className="mb-6">
        仓储AI分析
      </Title>

      {/* Summary Statistics */}
      {summary && (
        <Row gutter={16} className="mb-6">
          <Col span={6}>
            <Card>
              <Statistic
                title="原辅料总数"
                value={summary.raw_materials.total}
                suffix={
                  summary.raw_materials.low_stock > 0 ? (
                    <Tag color="warning">低库存 {summary.raw_materials.low_stock}</Tag>
                  ) : null
                }
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="包材总数"
                value={summary.packaging_materials.total}
                suffix={
                  summary.packaging_materials.low_stock > 0 ? (
                    <Tag color="warning">低库存 {summary.packaging_materials.low_stock}</Tag>
                  ) : null
                }
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="成品总数"
                value={summary.products.total}
                suffix={
                  summary.products.with_stock > 0 ? (
                    <Tag color="processing">有库存 {summary.products.with_stock}</Tag>
                  ) : null
                }
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="异常物料数"
                value={summary.summary.anomaly_count}
                styles={{
                  content: {
                    color: summary.summary.anomaly_count > 0 ? '#cf1322' : '#3f8600',
                  },
                }}
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* Tab Navigation */}
      <Space className="mb-4">
        <Button
          type={activeTab === 'anomalies' ? 'primary' : 'default'}
          icon={<AlertOutlined />}
          onClick={() => setActiveTab('anomalies')}
        >
          异常检测
        </Button>
        <Button
          type={activeTab === 'chat' ? 'primary' : 'default'}
          icon={<MessageOutlined />}
          onClick={() => setActiveTab('chat')}
        >
          智能问答
        </Button>
        <Button
          type={activeTab === 'report' ? 'primary' : 'default'}
          icon={<FileTextOutlined />}
          onClick={() => setActiveTab('report')}
        >
          分析报告
        </Button>
      </Space>

      {/* Content */}
      <Spin spinning={loading}>
        {activeTab === 'anomalies' && renderAnomalies()}
        {activeTab === 'chat' && renderChat()}
        {activeTab === 'report' && renderReport()}
      </Spin>
    </div>
  )
}
