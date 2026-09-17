'use client'

import { useCallback, useEffect, useState } from 'react'
import dayjs from 'dayjs'
import { BarChartOutlined } from '@ant-design/icons'
import {
  Card,
  Col,
  DatePicker,
  Progress,
  Row,
  Statistic,
  Table,
  Tabs,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { getPlans } from '@/actions/production'
import type { ProductionPlan } from '@/types/production'
import SyncSettingsButton from '@/components/production/SyncSettingsButton'
import { PRODUCTION_PAGE_KEYS } from '@/components/production/useProductionPermissions'

const { Title, Text } = Typography

const dash = '--'

// 汇总卡片占位：数据源接入前仅保留版面（口径：KG 与批分开统计）
const SUMMARY_PLACEHOLDERS = [
  { key: 'kg-planned', title: '计划产量（KG）' },
  { key: 'kg-actual', title: '实际完成（KG）' },
  { key: 'kg-rate', title: '完成率（KG）' },
  { key: 'batch-planned', title: '计划产量（批）' },
  { key: 'batch-actual', title: '实际完成（批）' },
  { key: 'batch-rate', title: '完成率（批）' },
]

// ═══════════════════════════════════════════
// 主页面：飞书同步的生产计划台账
// ═══════════════════════════════════════════
export default function PlanPage() {
  const [month, setMonth] = useState(dayjs().format('YYYY-MM'))
  const [plans, setPlans] = useState<ProductionPlan[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  const load = useCallback(async (p: number, m: string) => {
    setLoading(true)
    try {
      const res = await getPlans({ page: p, page_size: 20, month: m })
      if (res.code === 200) {
        setPlans(res.data || [])
        setTotal(res.meta?.total || 0)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(page, month) // eslint-disable-line react-hooks/set-state-in-effect
  }, [page, month, load])

  const changeMonth = (d: dayjs.Dayjs | null) => {
    if (!d) return
    setPage(1)
    setMonth(d.format('YYYY-MM'))
  }

  const columns: ColumnsType<ProductionPlan> = [
    { title: '车间', dataIndex: 'workshop', width: 130, render: (v: string | null) => v || '-' },
    { title: '产品', dataIndex: 'product_name', width: 140, render: (v: string) => v || '-' },
    { title: '日期', dataIndex: 'plan_date', width: 100, render: (v: string | null) => v || '-' },
    { title: '单位', dataIndex: 'unit', width: 60, render: (v: string | null) => v || '-' },
    {
      title: '计划产量',
      dataIndex: 'planned_yield',
      width: 100,
      render: (v: number | null) => (v != null ? v.toLocaleString('zh-CN') : '-'),
    },
    {
      title: '实际完成',
      dataIndex: 'actual_completion',
      width: 100,
      render: (v: number | null) => (v != null ? v.toLocaleString('zh-CN') : '-'),
    },
    {
      title: '完成率',
      dataIndex: 'completion_rate',
      width: 140,
      render: (v: number | null) => {
        if (v == null) return '-'
        const pct = Math.round(v * 1000) / 10
        return (
          <div className="flex items-center gap-2">
            <Progress
              percent={Math.min(100, pct)}
              size="small"
              showInfo={false}
              style={{ width: 72, margin: 0 }}
            />
            <span style={{ fontSize: 12 }}>{pct}%</span>
          </div>
        )
      },
    },
    { title: '安环情况', dataIndex: 'safety_status', width: 90, render: (v: string | null) => v || '-' },
    { title: '质量情况', dataIndex: 'quality_status', width: 90, render: (v: string | null) => v || '-' },
    { title: '备注', dataIndex: 'remarks', width: 150, ellipsis: true, render: (v: string | null) => v || '-' },
  ]

  return (
    <div className="p-6">
      <div className="mb-4">
        <Title level={4} style={{ margin: 0 }}>
          <BarChartOutlined className="mr-2" />
          产销计划
        </Title>
        <Text type="secondary">生产计划管理与飞书数据同步</Text>
      </div>

      <Tabs
        defaultActiveKey="plan"
        items={[
          {
            key: 'plan',
            label: '生产计划',
            children: (
              <>
                <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
                  {SUMMARY_PLACEHOLDERS.map((c) => (
                    <Col xs={24} md={8} key={c.key}>
                      <Card
                        variant="borderless"
                        className="shadow-sm h-full"
                        styles={{ body: { padding: '10px 14px' } }}
                      >
                        <Statistic
                          title={<span style={{ fontSize: 12 }}>{c.title}</span>}
                          value={dash}
                          styles={{ content: { fontSize: 24, fontWeight: 600 } }}
                        />
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          数据源待接入
                        </Text>
                      </Card>
                    </Col>
                  ))}
                </Row>

                <Card
                  variant="borderless"
                  className="shadow-sm"
                  styles={{ body: { padding: '12px 16px' } }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: 12,
                      flexWrap: 'wrap',
                      gap: 8,
                    }}
                  >
                    <DatePicker
                      size="small"
                      picker="month"
                      allowClear={false}
                      style={{ width: 96 }}
                      value={dayjs(`${month}-01`)}
                      onChange={changeMonth}
                    />
                    <SyncSettingsButton productName="生产计划" syncTarget="production_plan" pageKey={PRODUCTION_PAGE_KEYS.salesPlan} />
                  </div>
                  <Table
                    columns={columns}
                    dataSource={plans}
                    rowKey="id"
                    loading={loading}
                    size="small"
                    scroll={{ x: 1100 }}
                    pagination={{
                      current: page,
                      pageSize: 20,
                      total,
                      showSizeChanger: false,
                      showTotal: t => `共 ${t} 条`,
                      onChange: p => setPage(p),
                    }}
                  />
                </Card>
              </>
            ),
          },
        ]}
      />
    </div>
  )
}
