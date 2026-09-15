'use client'

import Link from 'next/link'
import { Alert, Card, Col, Row, Space, Statistic, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { fetchInstrumentsDashboard } from '@/lib/api/client/quality'
import type {
  InstrumentCalibrationDueRow,
  InstrumentContractDueRow,
} from '@/types/quality'

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
  { title: '来源', dataIndex: 'source', key: 'source', width: 120 },
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

const contractColumns: ColumnsType<InstrumentContractDueRow> = [
  {
    title: '合同',
    dataIndex: 'name',
    key: 'name',
    render: (value: string) => {
      const match = value?.match(/\[([^\]]+)\]/)
      return match ? match[1] : value || '-'
    },
  },
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

/** 仪器管理首页：概览 + 校验/合同到期提醒 + 各子表入口（数据读本地镜像）。 */
export function InstrumentsDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ['quality-instruments', 'dashboard'],
    queryFn: fetchInstrumentsDashboard,
  })

  const dueRows = [...(data?.calibration_expired ?? []), ...(data?.calibration_due ?? [])]

  return (
    <div style={{ padding: 24 }}>
      <Space direction="vertical" size={4} style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          仪器管理
        </Title>
        <Text type="secondary">
          仪器台账、维保、维修与校验计划总览；数据来自本地镜像，明细在各子表维护。
        </Text>
      </Space>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {!isLoading && data && !data.configured && (
          <Alert
            type="warning"
            showIcon
            title="镜像尚未同步"
            description="请先进入任意子表（如仪器台账）点击「同步飞书数据」，或等待定时同步完成后查看。"
          />
        )}
        <Row gutter={16}>
          <Col span={6}>
            <Card>
              <Statistic title="设备总数" value={data?.equipment.total ?? 0} />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="完好"
                value={data?.equipment.ok ?? 0}
                valueStyle={{ color: '#389e0d' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="维修中"
                value={data?.equipment.repairing ?? 0}
                valueStyle={{
                  color: (data?.equipment.repairing ?? 0) > 0 ? '#cf1322' : undefined,
                }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic title="重点设备" value={data?.equipment.key_count ?? 0} />
            </Card>
          </Col>
        </Row>

        <Row gutter={16}>
          <Col span={8}>
            <Card>
              <Statistic
                title="校验到期（30 天内 / 已过期）"
                value={dueRows.length}
                valueStyle={{ color: dueRows.length > 0 ? '#d46b08' : undefined }}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card>
              <Statistic
                title="未完成维保记录"
                value={data?.maintenance.unfinished ?? 0}
                suffix={`/ 共 ${data?.maintenance.total ?? 0} 条`}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card>
              <Statistic
                title="维保合同（含临期/到期）"
                value={data?.contracts.total ?? 0}
                suffix={data?.contracts.expiring.length ? `，临期 ${data.contracts.expiring.length}` : ''}
              />
            </Card>
          </Col>
        </Row>

        <Card
          title="校验到期提醒"
          extra={<Text type="secondary">含内校汇总 / 内部校验计划 / 外部校准检定</Text>}
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

        {(data?.contracts.expiring.length ?? 0) > 0 && (
          <Card title="维保合同到期提醒">
            <Table
              rowKey="record_id"
              size="small"
              columns={contractColumns}
              dataSource={data?.contracts.expiring}
              pagination={false}
            />
          </Card>
        )}

        <Card title="进入子表">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            {SECTION_ENTRIES.map((entry) => (
              <Link
                key={entry.href}
                href={entry.href}
                className="rounded border border-[var(--color-border)] px-3 py-2 text-sm hover:border-[var(--color-primary)]"
              >
                {entry.label}
              </Link>
            ))}
          </div>
        </Card>
      </Space>
    </div>
  )
}