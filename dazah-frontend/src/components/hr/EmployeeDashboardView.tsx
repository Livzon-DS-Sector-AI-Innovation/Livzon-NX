'use client'

import { Card, Col, Progress, Row, Statistic, Table, Tabs, Tag, Typography } from 'antd'
import {
  ApartmentOutlined,
  AuditOutlined,
  ClockCircleOutlined,
  FieldTimeOutlined,
  FileExclamationOutlined,
  ReadOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
  UserAddOutlined,
  UserDeleteOutlined,
  UserOutlined,
} from '@ant-design/icons'
import Link from 'next/link'
import type { ReactNode } from 'react'
import type {
  CertificateDueItem,
  ContractExpiringItem,
  EmployeeStats,
  ProbationDueItem,
} from '@/types/hr'

interface Props {
  stats: EmployeeStats
}

interface SummaryCard {
  title: string
  value: number
  icon: ReactNode
  color?: string
}

const responsiveSpan = { xs: 12, sm: 8, lg: 4 }

export default function EmployeeDashboardView({ stats }: Props) {
  const deptCount = stats.department_distribution?.length || 0
  // 飞书同步档案状态为“正式”，本地创建默认“在职”，两类都计入正式员工
  const statusCounts = stats.status_distribution || {}
  const formalCount = (statusCounts['正式'] || 0) + (statusCounts['在职'] || 0)
  const probationCount = statusCounts['试用期'] || 0
  const internCount = statusCounts['实习生'] || 0

  const summaryCards: SummaryCard[] = [
    { title: '员工总数', value: stats.total || 0, icon: <UserOutlined /> },
    { title: '正式员工', value: formalCount, icon: <TeamOutlined />, color: '#52c41a' },
    { title: '试用期', value: probationCount, icon: <ClockCircleOutlined /> },
    { title: '实习生', value: internCount, icon: <ReadOutlined /> },
    { title: '部门数', value: deptCount, icon: <ApartmentOutlined /> },
    { title: '本月入职', value: stats.hires_this_month || 0, icon: <UserAddOutlined /> },
    { title: '本月离职', value: stats.departures_this_month || 0, icon: <UserDeleteOutlined /> },
    { title: '合同到期·本季度', value: stats.contract_expiring_count || 0, icon: <FileExclamationOutlined />, color: '#fa8c16' },
    { title: '合同到期·未来90天', value: stats.contract_expiring_90d_count || 0, icon: <FieldTimeOutlined />, color: '#fa8c16' },
    { title: '试用期转正·30天内', value: stats.probation_due_count || 0, icon: <AuditOutlined /> },
    { title: '证书复审·90天内', value: stats.certificate_due_count || 0, icon: <SafetyCertificateOutlined /> },
  ]

  const deptColumns = [
    {
      title: '部门',
      dataIndex: 'department',
      key: 'department',
      render: (department: string) => (
        <Link href={`/hr/profile?department=${encodeURIComponent(department)}`}>
          {department}
        </Link>
      ),
    },
    { title: '人数', dataIndex: 'count', key: 'count', width: 80, render: (c: number) => <Tag color="blue">{c}</Tag> },
    {
      title: '占比',
      key: 'ratio',
      width: 120,
      render: (_: unknown, record: { count: number }) => (
        <Progress
          percent={stats.total ? Math.round((record.count / stats.total) * 100) : 0}
          size="small"
        />
      ),
    },
  ]

  const expiringColumns = [
    { title: '工号', dataIndex: 'employee_number', key: 'employee_number', width: 100 },
    { title: '姓名', dataIndex: 'name', key: 'name', width: 80 },
    { title: '部门', dataIndex: 'department', key: 'department' },
    { title: '岗位', dataIndex: 'position', key: 'position' },
    { title: '第N次合同', dataIndex: 'contract_sequence', key: 'contract_sequence', width: 100, render: (v: number | undefined) => (v ? `第${v}次` : '-') },
    { title: '签订日期', dataIndex: 'contract_sign_date', key: 'contract_sign_date', width: 110, render: (v: string | null) => v || '-' },
    {
      title: '到期日',
      dataIndex: 'contract_end_date',
      key: 'contract_end_date',
      width: 110,
      render: (v: string | null) => (v ? <Tag color="orange">{v}</Tag> : '-'),
    },
  ]

  const probationColumns = [
    { title: '工号', dataIndex: 'employee_number', key: 'employee_number', width: 100 },
    { title: '姓名', dataIndex: 'name', key: 'name', width: 80 },
    { title: '部门', dataIndex: 'department', key: 'department' },
    { title: '岗位', dataIndex: 'position', key: 'position' },
    {
      title: '计划转正日期',
      dataIndex: 'planned_probation_date',
      key: 'planned_probation_date',
      width: 130,
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
  ]

  const certificateColumns = [
    { title: '工号', dataIndex: 'employee_number', key: 'employee_number', width: 100 },
    { title: '姓名', dataIndex: 'name', key: 'name', width: 80 },
    { title: '部门', dataIndex: 'department', key: 'department' },
    { title: '岗位', dataIndex: 'position', key: 'position' },
    { title: '资格类型', dataIndex: 'qualification_type', key: 'qualification_type', render: (v: string | null | undefined) => v || '-' },
    {
      title: '复审到期',
      dataIndex: 'certificate_review_date',
      key: 'certificate_review_date',
      width: 120,
      render: (v: string) => <Tag color="red">{v}</Tag>,
    },
  ]

  const paginated = (rows: unknown[]) =>
    rows.length > 10 ? { pageSize: 10 } : false

  const tabItems = [
    {
      key: 'quarter',
      label: `合同到期·本季度 (${stats.contract_expiring_count || 0})`,
      children: (
        <Table<ContractExpiringItem>
          rowKey="employee_number"
          columns={expiringColumns}
          dataSource={stats.contract_expiring_list || []}
          pagination={paginated(stats.contract_expiring_list || [])}
          size="small"
        />
      ),
    },
    {
      key: 'next90d',
      label: `合同到期·未来90天 (${stats.contract_expiring_90d_count || 0})`,
      children: (
        <Table<ContractExpiringItem>
          rowKey="employee_number"
          columns={expiringColumns}
          dataSource={stats.contract_expiring_90d_list || []}
          pagination={paginated(stats.contract_expiring_90d_list || [])}
          size="small"
        />
      ),
    },
    {
      key: 'probation',
      label: `试用期转正·30天内 (${stats.probation_due_count || 0})`,
      children: (
        <Table<ProbationDueItem>
          rowKey="employee_number"
          columns={probationColumns}
          dataSource={stats.probation_due_list || []}
          pagination={paginated(stats.probation_due_list || [])}
          size="small"
        />
      ),
    },
    {
      key: 'certificate',
      label: `证书复审·90天内 (${stats.certificate_due_count || 0})`,
      children: (
        <Table<CertificateDueItem>
          rowKey="employee_number"
          columns={certificateColumns}
          dataSource={stats.certificate_due_list || []}
          pagination={paginated(stats.certificate_due_list || [])}
          size="small"
        />
      ),
    },
  ]

  return (
    <>
      <Row gutter={[16, 16]}>
        {summaryCards.map((card) => (
          <Col key={card.title} {...responsiveSpan}>
            <Card>
              <Statistic
                title={card.title}
                value={card.value}
                prefix={card.icon}
                styles={card.color ? { content: { color: card.color } } : undefined}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={16}>
        <Col xs={24} lg={12}>
          <Card title="部门分布（点击部门查看员工档案）">
            <Table
              rowKey="department"
              columns={deptColumns}
              dataSource={stats.department_distribution || []}
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="学历分布">
            <div className="space-y-2">
              {Object.entries(stats.education_distribution || {}).map(([k, v]) => (
                <div key={k}>
                  <Typography.Text>{k}: {v}人</Typography.Text>
                  <Progress percent={stats.total ? Math.round((v / stats.total) * 100) : 0} size="small" />
                </div>
              ))}
            </div>
          </Card>
        </Col>
      </Row>

      <Card title="提醒中心">
        <Tabs items={tabItems} />
      </Card>
    </>
  )
}
