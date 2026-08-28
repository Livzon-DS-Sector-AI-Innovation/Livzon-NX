'use client'

import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd'
import { CloudUploadOutlined, ReloadOutlined, RiseOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState, useTransition } from 'react'

import { syncInspectionRecordToFeishu } from '@/actions/quality'
import {
  fetchInspectionDashboard,
  fetchInspectionTrend,
  type InspectionDashboardResponse,
  type InspectionDashboardLatestRecord,
} from '@/lib/api/quality-inspection'

type LatestRecord = InspectionDashboardLatestRecord
type TrendSelection = Pick<LatestRecord, 'resource_code' | 'subject' | 'inspection_item'>

const TREND_RESOURCE_CODES = new Set([
  'inspection_records',
  'finished_product_inspections',
  'solid_material_inspections',
  'liquid_material_inspections',
])

function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleDateString('zh-CN') : '-'
}

function conclusionTag(value: string | null | undefined) {
  if (!value) return <Tag>待判定</Tag>
  if (['合格', '通过', '正常'].includes(value)) return <Tag color="success">{value}</Tag>
  return <Tag color="error">{value}</Tag>
}

export function InspectionDashboardPage() {
  const [selection, setSelection] = useState<TrendSelection | null>(null)
  const [notice, setNotice] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(
    null,
  )
  const [syncingRecordId, setSyncingRecordId] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()
  const dashboardQuery = useQuery({
    queryKey: ['quality-inspection-dashboard'],
    queryFn: fetchInspectionDashboard,
  })
  const trendQuery = useQuery({
    queryKey: [
      'quality-inspection-trend',
      selection?.resource_code,
      selection?.subject,
      selection?.inspection_item,
    ],
    queryFn: () =>
      fetchInspectionTrend({
        resource_code: selection!.resource_code,
        subject: selection?.subject || undefined,
        inspection_item: selection?.inspection_item || undefined,
        limit: 50,
      }),
    enabled: Boolean(selection),
  })

  const records = dashboardQuery.data?.latest_records ?? []
  const columns = useMemo(
    () => [
      {
        title: '资源',
        dataIndex: 'resource_name',
        key: 'resource_name',
        width: 130,
      },
      {
        title: '检验编号 / 批号',
        key: 'identifier',
        render: (_: unknown, record: LatestRecord) => (
          <Space direction="vertical" size={0}>
            <Typography.Text strong>{record.inspection_no || '-'}</Typography.Text>
            <Typography.Text type="secondary">{record.batch_no || '-'}</Typography.Text>
          </Space>
        ),
      },
      {
        title: '产品或物料',
        dataIndex: 'subject',
        key: 'subject',
        render: (value: string | null) => value || '-',
      },
      {
        title: '项目 / 结果',
        key: 'result',
        render: (_: unknown, record: LatestRecord) => (
          <Space direction="vertical" size={0}>
            <Typography.Text>{record.inspection_item || '-'}</Typography.Text>
            <Typography.Text type="secondary">{record.test_result || '-'}</Typography.Text>
          </Space>
        ),
      },
      {
        title: '结论',
        dataIndex: 'conclusion',
        key: 'conclusion',
        width: 100,
        render: conclusionTag,
      },
      {
        title: '检验日期',
        dataIndex: 'inspection_date',
        key: 'inspection_date',
        width: 120,
        render: formatDate,
      },
      {
        title: '操作',
        key: 'actions',
        width: 210,
        render: (_: unknown, record: LatestRecord) => (
          <Space>
            <Button
              size="small"
              disabled={!TREND_RESOURCE_CODES.has(record.resource_code)}
              icon={<RiseOutlined />}
              onClick={() =>
                setSelection({
                  resource_code: record.resource_code,
                  subject: record.subject,
                  inspection_item: record.inspection_item,
                })
              }
            >
              趋势
            </Button>
            <Button
              size="small"
              icon={<CloudUploadOutlined />}
              loading={isPending && syncingRecordId === record.id}
              onClick={() => {
                setSyncingRecordId(record.id)
                startTransition(async () => {
                  try {
                    const result = await syncInspectionRecordToFeishu(
                      record.resource_code,
                      record.id,
                    )
                    setNotice({
                      type: 'success',
                      text: `已推送至飞书表 ${result.table_id}`,
                    })
                  } catch (error) {
                    setNotice({
                      type: 'error',
                      text: error instanceof Error ? error.message : '推送至飞书失败',
                    })
                  } finally {
                    setSyncingRecordId(null)
                  }
                })
              }}
            >
              推送飞书
            </Button>
          </Space>
        ),
      },
    ],
    [isPending, syncingRecordId, startTransition],
  )

  if (dashboardQuery.isLoading) {
    return <Spin size="large" />
  }

  if (dashboardQuery.error) {
    return (
      <Alert
        type="error"
        showIcon
        title="检验看板加载失败"
        description={dashboardQuery.error.message}
        action={<Button onClick={() => void dashboardQuery.refetch()}>重试</Button>}
      />
    )
  }

  const dashboard: InspectionDashboardResponse | undefined = dashboardQuery.data
  return (
    <Space direction="vertical" size={16} style={{ display: 'flex' }}>
      <div>
        <Typography.Title level={3} style={{ marginBottom: 4 }}>
          检验管理
        </Typography.Title>
        <Typography.Text type="secondary">
          平台数据库是检验事实来源；飞书仅在确认后推送单条记录。
        </Typography.Text>
      </div>

      {notice ? (
        <Alert
          closable
          showIcon
          type={notice.type}
          title={notice.text}
          onClose={() => setNotice(null)}
        />
      ) : null}

      <Row gutter={[16, 16]}>
        {dashboard?.resource_summaries.map((summary) => (
          <Col key={summary.resource_code} xs={24} sm={12} lg={8} xl={6}>
            <Card size="small">
              <Statistic title={summary.resource_name} value={summary.total} suffix="条" />
              <Space size={12} style={{ marginTop: 8 }}>
                <Typography.Text type="success">合格 {summary.qualified}</Typography.Text>
                <Typography.Text type="danger">
                  关注 {summary.attention_required}
                </Typography.Text>
              </Space>
            </Card>
          </Col>
        ))}
      </Row>

      <Card
        title="最新检验记录"
        extra={
          <Button
            icon={<ReloadOutlined />}
            loading={dashboardQuery.isFetching}
            onClick={() => void dashboardQuery.refetch()}
          >
            刷新
          </Button>
        }
      >
        <Table<LatestRecord>
          rowKey="id"
          columns={columns}
          dataSource={records}
          pagination={false}
          scroll={{ x: 1100 }}
          locale={{ emptyText: <Empty description="暂无检验记录" /> }}
        />
      </Card>

      <Card title="检验结果趋势与预警">
        {!selection ? (
          <Empty description="从最新检验记录选择“趋势”后，查看同一产品或物料的检验结果变化。" />
        ) : trendQuery.isLoading ? (
          <Spin />
        ) : trendQuery.error ? (
          <Alert
            type="error"
            showIcon
            title="趋势数据加载失败"
            description={trendQuery.error.message}
          />
        ) : trendQuery.data ? (
          <Space direction="vertical" size={16} style={{ display: 'flex' }}>
            <Space wrap>
              <Tag color="blue">{trendQuery.data.resource_name}</Tag>
              {trendQuery.data.subject ? <Tag>{trendQuery.data.subject}</Tag> : null}
              {trendQuery.data.inspection_item ? (
                <Tag>{trendQuery.data.inspection_item}</Tag>
              ) : null}
              <Typography.Text>样本 {trendQuery.data.summary.sample_count}</Typography.Text>
              <Typography.Text>
                均值 {trendQuery.data.summary.mean?.toFixed(3) ?? '-'}
              </Typography.Text>
              <Typography.Text type="danger">
                预警 {trendQuery.data.summary.alert_count}
              </Typography.Text>
            </Space>
            {trendQuery.data.alerts.length ? (
              <Alert
                type="warning"
                showIcon
                title={`发现 ${trendQuery.data.alerts.length} 条趋势预警`}
                description={trendQuery.data.alerts
                  .map((alert) => `${alert.label}：${alert.message}`)
                  .join('；')}
              />
            ) : null}
            <Table
              rowKey="record_id"
              size="small"
              pagination={false}
              dataSource={trendQuery.data.points}
              columns={[
                { title: '批号 / 编号', dataIndex: 'label', key: 'label' },
                {
                  title: '检验日期',
                  dataIndex: 'inspection_date',
                  key: 'inspection_date',
                  render: formatDate,
                },
                { title: '结果', dataIndex: 'value', key: 'value' },
                { title: '标准规定', dataIndex: 'specification', key: 'specification' },
                {
                  title: '状态',
                  dataIndex: 'is_alert',
                  key: 'is_alert',
                  render: (isAlert: boolean) =>
                    isAlert ? <Tag color="error">预警</Tag> : <Tag color="success">正常</Tag>,
                },
              ]}
            />
          </Space>
        ) : null}
      </Card>
    </Space>
  )
}
