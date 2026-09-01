'use client'

import { useState } from 'react'
import { Card, Col, Row, Statistic, Table, Tag, Progress, Typography, Space, Button } from 'antd'
import { UserOutlined, TeamOutlined, FileExclamationOutlined, ApartmentOutlined, QrcodeOutlined } from '@ant-design/icons'
import type { EmployeeStats } from '@/types/hr'
import EmployeeQrCode from './EmployeeQrCode'

interface Props {
  stats: EmployeeStats
}

export default function EmployeeDashboardClient({ stats }: Props) {
  const [qrOpen, setQrOpen] = useState(false)
  const deptCount = stats.department_distribution?.length || 0
  const activeCount = stats.status_distribution?.['在职'] || 0

  const deptColumns = [
    { title: '部门', dataIndex: 'department', key: 'department' },
    { title: '人数', dataIndex: 'count', key: 'count', width: 80, render: (c: number) => <Tag color="blue">{c}</Tag> },
  ]

  const expiringColumns = [
    { title: '工号', dataIndex: 'employee_number', key: 'employee_number', width: 90 },
    { title: '姓名', dataIndex: 'name', key: 'name', width: 80 },
    { title: '部门', dataIndex: 'department', key: 'department' },
    { title: '岗位', dataIndex: 'position', key: 'position' },
    {
      title: '合同到期日',
      dataIndex: 'contract_end_date',
      key: 'contract_end_date',
      width: 120,
      render: (v: string) => v ? <Tag color="orange">{v}</Tag> : '-',
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">员工管理</h1>
        <Button icon={<QrcodeOutlined />} onClick={() => setQrOpen(true)}>生成填写二维码</Button>
      </div>
      <EmployeeQrCode open={qrOpen} onClose={() => setQrOpen(false)} />

      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic title="员工总数" value={stats.total || 0} prefix={<UserOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="在职人数" value={activeCount} prefix={<TeamOutlined />} styles={{ content: { color: '#52c41a' } }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="合同即将到期" value={stats.contract_expiring_count || 0} prefix={<FileExclamationOutlined />} styles={{ content: { color: '#fa8c16' } }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="部门数" value={deptCount} prefix={<ApartmentOutlined />} />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Card title="部门分布">
            <Table
              rowKey="department"
              columns={deptColumns}
              dataSource={stats.department_distribution || []}
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="学历分布">
            <Space orientation="vertical" style={{ width: '100%' }}>
              {Object.entries(stats.education_distribution || {}).map(([k, v]) => (
                <div key={k}>
                  <Typography.Text>{k}: {v}人</Typography.Text>
                  <Progress percent={stats.total ? Math.round((v / stats.total) * 100) : 0} size="small" />
                </div>
              ))}
            </Space>
          </Card>
        </Col>
      </Row>

      <Card title="合同即将到期详情（本季度）">
        <Table
          rowKey="employee_number"
          columns={expiringColumns}
          dataSource={stats.contract_expiring_list || []}
          pagination={(stats.contract_expiring_list?.length || 0) > 10 ? { pageSize: 10 } : false}
          size="small"
        />
      </Card>
    </div>
  )
}
