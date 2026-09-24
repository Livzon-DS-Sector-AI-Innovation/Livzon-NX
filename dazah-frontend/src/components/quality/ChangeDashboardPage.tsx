'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { Button, Card, Col, Empty, Modal, Row, Select, Space, Spin, Statistic, Table, Tag, Tooltip } from 'antd'
import type { TableColumnsType } from 'antd'
import { useQuery } from '@tanstack/react-query'
import ReactECharts from 'echarts-for-react'
import { fetchChangeActionPlanDueStatus, fetchChangeDashboardStats } from '@/lib/api/client/quality'
import type { ChangeActionPlanDueStatusItem } from '@/types/quality'
import { PersonCell } from './index'


const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  pending_approval: '待批准',
  in_execution: '执行中',
  closed: '已关闭',
}

const DUE_WINDOW_OPTIONS = [
  { label: '10 天内', value: 10 },
  { label: '15 天内', value: 15 },
  { label: '30 天内', value: 30 },
]

type DueBucket = 'overdue' | 'due_soon'

const BUCKET_TITLES: Record<DueBucket, string> = {
  overdue: '逾期计划明细',
  due_soon: '临期计划明细',
}

function formatDate(value: string | null): string {
  return value ? value.slice(0, 10) : '-'
}

export function ChangeDashboardPage() {
  const [dueWindow, setDueWindow] = useState(15)
  const [detailBucket, setDetailBucket] = useState<DueBucket | null>(null)

  const { data: stats, isLoading: loading } = useQuery({
    queryKey: ['quality-stats', 'change'],
    queryFn: fetchChangeDashboardStats,
  })

  const { data: dueStatus, isLoading: dueLoading } = useQuery({
    queryKey: ['quality-change-plan-due-status', dueWindow],
    queryFn: () => fetchChangeActionPlanDueStatus(dueWindow),
  })

  const statusChartOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: stats?.statusDistribution.map(s => STATUS_LABELS[s.status] || s.status) || [] },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: stats?.statusDistribution.map(s => s.count) || [], itemStyle: { color: '#2563eb' } }],
  }

  const levelChartOption = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      data: stats?.levelDistribution.map(l => ({ name: l.level, value: l.count })) || [],
    }],
  }

  const deptChartOption = {
    tooltip: { trigger: 'item' },
    legend: { type: 'scroll', bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      data: stats?.departmentDistribution.map(d => ({ name: d.name, value: d.count })) || [],
    }],
  }

  const isOverdueBucket = detailBucket === 'overdue'

  const detailColumns = useMemo<TableColumnsType<ChangeActionPlanDueStatusItem>>(
    () => [
      {
        title: '变更控制号',
        dataIndex: 'change_code',
        width: 130,
        render: (value: string | null) => value || '-',
      },
      {
        title: '项目名称',
        dataIndex: 'project_name',
        render: (value: string | null) => (
          <Tooltip title={value || '-'}>
            <div style={{ whiteSpace: 'normal', wordBreak: 'break-all' }}>{value || '-'}</div>
          </Tooltip>
        ),
      },
      {
        title: '总负责人',
        dataIndex: 'owner_name',
        width: 120,
        render: (value: string | null, record) => (
          <PersonCell name={value} avatarUrl={record.owner_avatar_url || null} />
        ),
      },
      {
        title: '截止时间',
        key: 'deadline',
        width: 150,
        render: (_, record) => (
          <Space size={4}>
            <span>{formatDate(record.delayed_deadline_date || record.deadline_date)}</span>
            {record.delayed_deadline_date ? <Tag color="orange">已延期</Tag> : null}
          </Space>
        ),
      },
      { title: '状态', dataIndex: 'status', width: 90, render: (value: string | null) => value || '-' },
      {
        title: isOverdueBucket ? '逾期天数' : '剩余天数',
        key: 'days_offset',
        width: 100,
        render: (_, record) =>
          isOverdueBucket || record.days_offset < 0 ? (
            <span style={{ color: '#cf1322' }}>{record.days_offset < 0 ? `逾期 ${-record.days_offset} 天` : '今天到期'}</span>
          ) : record.days_offset === 0 ? (
            <span style={{ color: '#d46b08' }}>今天到期</span>
          ) : (
            <span>剩余 {record.days_offset} 天</span>
          ),
      },
    ],
    [isOverdueBucket],
  )

  const detailItems = detailBucket ? dueStatus?.[detailBucket] ?? [] : []

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 变更控制</p>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>变更控制仪表盘</h1>
      </div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Link href="/quality/change/ledger"><Button type="primary">进入技术变更台账</Button></Link>
        <Link href="/quality/change/action-plans"><Button>进入变更计划</Button></Link>
      </Space>
      <Spin spinning={loading || dueLoading}>
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} lg={8}>
            <Card><Statistic title="变更总数" value={stats?.total ?? 0} /></Card>
          </Col>
          <Col xs={24} sm={12} lg={8}>
            <Card><Statistic title="变更计划总数" value={dueStatus?.total_count ?? stats?.actionPlanTotal ?? 0} /></Card>
          </Col>
          <Col xs={24} sm={12} lg={8}>
            <Card hoverable style={{ cursor: 'pointer' }} onClick={() => setDetailBucket('overdue')}>
              <Statistic title="逾期计划（点击查看明细）" value={dueStatus?.overdue.length ?? 0} styles={{ content: { color: '#cf1322' } }} />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={8}>
            <Card hoverable style={{ cursor: 'pointer' }} onClick={() => setDetailBucket('due_soon')}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <span style={{ color: 'rgba(0, 0, 0, 0.45)', fontSize: 14 }}>临期计划（点击查看明细）</span>
                <Select
                  size="small"
                  value={dueWindow}
                  options={DUE_WINDOW_OPTIONS}
                  onChange={setDueWindow}
                  style={{ width: 92 }}
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
              <Statistic value={dueStatus?.due_soon.length ?? 0} styles={{ content: { color: '#d46b08' } }} />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={8}>
            <Card><Statistic title="已确认提醒" value={dueStatus?.confirmed_count ?? stats?.actionPlanConfirmed ?? 0} /></Card>
          </Col>
          <Col xs={24} md={8}>
            <Card title="状态分布">
              {stats?.statusDistribution.length ? (
                <ReactECharts option={statusChartOption} style={{ height: 300 }} />
              ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />}
            </Card>
          </Col>
          <Col xs={24} md={8}>
            <Card title="等级分布">
              {stats?.levelDistribution.length ? (
                <ReactECharts option={levelChartOption} style={{ height: 300 }} />
              ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />}
            </Card>
          </Col>
          <Col xs={24} md={8}>
            <Card title="部门分布">
              {stats?.departmentDistribution.length ? (
                <ReactECharts option={deptChartOption} style={{ height: 300 }} />
              ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />}
            </Card>
          </Col>
        </Row>
      </Spin>
      <Modal
        open={detailBucket !== null}
        title={detailBucket ? BUCKET_TITLES[detailBucket] + (detailBucket === 'due_soon' ? `（未来 ${dueWindow} 天内到期）` : '') : ''}
        footer={null}
        width={960}
        onCancel={() => setDetailBucket(null)}
      >
        <Table
          rowKey="id"
          size="small"
          columns={detailColumns}
          dataSource={detailItems}
          pagination={{ pageSize: 10, showSizeChanger: false }}
        />
      </Modal>
    </div>
  )
}
