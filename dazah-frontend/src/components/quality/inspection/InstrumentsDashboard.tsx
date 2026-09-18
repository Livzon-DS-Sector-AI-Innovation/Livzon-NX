'use client'

import Link from 'next/link'
import { Alert, Card, Col, Row, Space, Statistic, Table, Tag, Typography } from 'antd'
import { RightOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { useQuery } from '@tanstack/react-query'
import { fetchInstrumentsDashboard } from '@/lib/api/client/quality'
import type { InstrumentCalibrationDueRow } from '@/types/quality'

const { Title, Text } = Typography

const SECTION_ENTRIES: { label: string; href: string }[] = [
  { label: '仪器台账', href: '/quality/inspection/instruments/equipment' },
  { label: '维护保养记录', href: '/quality/inspection/instruments/maintenance' },
  { label: '维修记录', href: '/quality/inspection/instruments/repair' },
  { label: '维保合同', href: '/quality/inspection/instruments/contracts' },
  { label: '维保周期表', href: '/quality/inspection/instruments/plans' },
  { label: '内校汇总', href: '/quality/inspection/instruments/calibration' },
  { label: '内部校验计划', href: '/quality/inspection/instruments/cal-plan' },
  { label: '外部校准检定', href: '/quality/inspection/instruments/cal-external' },
]

function dueTag(days: number) {
  if (days < 0) return <Tag color="red">已过期 {-days} 天</Tag>
  if (days <= 7) return <Tag color="orange">{days} 天内</Tag>
  return <Tag color="gold">{days} 天内</Tag>
}

const calibrationColumns: ColumnsType<InstrumentCalibrationDueRow> = [
  { title: '来源', dataIndex: 'source', key: 'source', width: 140 },
  { title: '仪器/器具名称', dataIndex: 'name', key: 'name' },
  { title: '编号', dataIndex: 'code', key: 'code', width: 150 },
  {
    title: '有效期',
    dataIndex: 'due_date',
    key: 'due_date',
    width: 120,
    render: (value: string | null) => value || '-',
  },
  {
    title: '剩余',
    dataIndex: 'days',
    key: 'days',
    width: 110,
    render: (days: number) => dueTag(days),
  },
]

/** 统计卡：大数字只放主指标，细分口径用小标签放数字下方 */
function StatCard({
  title,
  value,
  valueColor,
  children,
}: {
  title: string
  value: number
  valueColor?: string
  children?: React.ReactNode
}) {
  return (
    <Card>
      <Statistic
        title={title}
        value={value}
        styles={valueColor ? { content: { color: valueColor } } : undefined}
      />
      <div style={{ marginTop: 8, minHeight: 22 }}>{children}</div>
    </Card>
  )
}

function percent(part: number, total: number): string {
  if (total <= 0) return '0'
  return String(Math.round((100 * part) / total))
}

const STATUS_COLORS: Record<string, string> = {
  完好: '#52c41a',
  维修: '#cf1322',
  未知: '#bfbfbf',
  未填写: '#bfbfbf',
}

const BUCKET_COLORS = ['#cf1322', '#fa8c16', '#faad14', '#1677ff', '#8c8c8c']

function buildStatusOption(
  data: { name: string; value: number }[]
): EChartsOption {
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, left: 'center', icon: 'circle', itemWidth: 8, itemHeight: 8 },
    series: [
      {
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '44%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        data: data.map((item) => ({
          ...item,
          itemStyle: { color: STATUS_COLORS[item.name] ?? '#5645d4' },
        })),
      },
    ],
  }
}

function buildBarOption(
  categories: string[],
  values: number[],
  colors?: string[]
): EChartsOption {
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 24, bottom: 28 },
    xAxis: { type: 'category', data: categories },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        type: 'bar',
        barMaxWidth: 36,
        data: values.map((value, index) => ({
          value,
          itemStyle: { color: colors ? colors[index] : '#5645d4' },
        })),
        label: { show: true, position: 'top' },
      },
    ],
  }
}

function monthLabel(month: string): string {
  const [, m] = month.split('-')
  return `${Number(m)}月`
}

/** 仪器管理首页：概览 + 校验到期提醒 + 各子表入口（数据读本地镜像）。 */
export function InstrumentsDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ['quality-instruments', 'dashboard'],
    queryFn: fetchInstrumentsDashboard,
  })

  const calibrationExpired = data?.calibration_expired ?? []
  const calibrationDue = data?.calibration_due ?? []
  const dueRows = [...calibrationExpired, ...calibrationDue]
  const dueIn7d = calibrationDue.filter((row) => row.days >= 0 && row.days <= 7).length
  const dueIn30d = calibrationDue.filter((row) => row.days > 7).length
  const equipmentTotal = data?.equipment.total ?? 0
  const maintenanceDue7d = data?.maintenance.due_soon_7d ?? 0

  return (
    <div style={{ padding: 24 }}>
      <Space orientation="vertical" size={4} style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          仪器管理
        </Title>
        <Text type="secondary">
          仪器台账、维保、维修与校验计划总览；数据来自本地镜像，明细在各子表维护。
        </Text>
      </Space>
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        {!isLoading && data && !data.configured && (
          <Alert
            type="warning"
            showIcon
            title="镜像尚未同步"
            description="请先进入任意子表（如仪器台账）点击「同步飞书数据」，或等待定时同步完成后查看。"
          />
        )}

        {/* 设备概览 */}
        <Row gutter={16}>
          <Col span={6}>
            <StatCard title="设备总数" value={equipmentTotal}>
              <Text type="secondary">在册仪器设备</Text>
            </StatCard>
          </Col>
          <Col span={6}>
            <StatCard
              title="完好"
              value={data?.equipment.ok ?? 0}
              valueColor="#389e0d"
            >
              <Text type="secondary">完好率 {percent(data?.equipment.ok ?? 0, equipmentTotal)}%</Text>
            </StatCard>
          </Col>
          <Col span={6}>
            <StatCard
              title="维修中"
              value={data?.equipment.repairing ?? 0}
              valueColor={(data?.equipment.repairing ?? 0) > 0 ? '#cf1322' : undefined}
            >
              <Text type="secondary">
                {(data?.equipment.repairing ?? 0) > 0 ? '需跟进维修' : '当前无维修中设备'}
              </Text>
            </StatCard>
          </Col>
          <Col span={6}>
            <StatCard title="重点设备" value={data?.equipment.key_count ?? 0}>
              <Text type="secondary">
                占比 {percent(data?.equipment.key_count ?? 0, equipmentTotal)}%
              </Text>
            </StatCard>
          </Col>
        </Row>

        {/* 待办与风险 */}
        <Row gutter={16}>
          <Col span={8}>
            <StatCard
              title="校验到期（30 天内 / 已过期）"
              value={dueRows.length}
              valueColor={dueRows.length > 0 ? '#d46b08' : undefined}
            >
              {dueRows.length === 0 ? (
                <Text type="secondary">30 天内无到期或已过期校验</Text>
              ) : (
                <Space size={4} wrap>
                  {calibrationExpired.length > 0 && (
                    <Tag color="red">已过期 {calibrationExpired.length}</Tag>
                  )}
                  {dueIn7d > 0 && <Tag color="orange">7 天内 {dueIn7d}</Tag>}
                  {dueIn30d > 0 && <Tag color="gold">30 天内 {dueIn30d}</Tag>}
                </Space>
              )}
            </StatCard>
          </Col>
          <Col span={8}>
            <StatCard title="未完成维保记录" value={data?.maintenance.unfinished ?? 0}>
              <Space size={4} wrap>
                <Text type="secondary">共 {data?.maintenance.total ?? 0} 条</Text>
                {maintenanceDue7d > 0 ? (
                  <Tag color="orange">7 天内到期 {maintenanceDue7d}</Tag>
                ) : (
                  <Text type="secondary">· 7 天内到期 0</Text>
                )}
              </Space>
            </StatCard>
          </Col>
          <Col span={8}>
            <StatCard title="维保合同" value={data?.contracts.total ?? 0}>
              <Text type="secondary">在管维保合同</Text>
            </StatCard>
          </Col>
        </Row>

        {/* 图表：构成 / 分布 */}
        <Row gutter={16}>
          <Col span={8}>
            <Card title="设备状态构成">
              <ReactECharts
                option={buildStatusOption(data?.equipment_status ?? [])}
                style={{ height: 240 }}
                notMerge
                lazyUpdate
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card title="未来 6 个月校验分布">
              <ReactECharts
                option={buildBarOption(
                  (data?.calibration_upcoming ?? []).map((item) => monthLabel(item.month)),
                  (data?.calibration_upcoming ?? []).map((item) => item.count)
                )}
                style={{ height: 240 }}
                notMerge
                lazyUpdate
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card title="未完成维保到期分布">
              <ReactECharts
                option={buildBarOption(
                  (data?.maintenance_due_buckets ?? []).map((item) => item.name),
                  (data?.maintenance_due_buckets ?? []).map((item) => item.value),
                  BUCKET_COLORS
                )}
                style={{ height: 240 }}
                notMerge
                lazyUpdate
              />
            </Card>
          </Col>
        </Row>

        <Card
          title="校验到期提醒"
          extra={<Text type="secondary">含内校汇总 / 外部校准检定，30 天内到期或已过期</Text>}
        >
          <Table
            rowKey={(row) => `${row.source}-${row.record_id}`}
            size="small"
            columns={calibrationColumns}
            dataSource={dueRows}
            loading={isLoading}
            pagination={false}
            locale={{ emptyText: '暂无 30 天内到期或已过期的校验' }}
          />
        </Card>

        <Card title="进入子表">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {SECTION_ENTRIES.map((entry) => (
              <Link
                key={entry.href}
                href={entry.href}
                className="group flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-white px-4 py-3 text-sm transition-colors hover:border-[var(--color-primary)] hover:bg-[#f3f0ff]"
              >
                <span>{entry.label}</span>
                <RightOutlined className="text-[12px] text-[var(--color-stone)] transition-transform group-hover:translate-x-0.5 group-hover:text-[var(--color-primary)]" />
              </Link>
            ))}
          </div>
        </Card>
      </Space>
    </div>
  )
}
