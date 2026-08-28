'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Card,
  Row,
  Col,
  Statistic,
  Tag,
  Typography,
  Space,
  Spin,
  Table,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  DashboardOutlined,
  FormOutlined,
  CameraOutlined,
  UnorderedListOutlined,
  EnvironmentOutlined,
  AuditOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons'
import { getPressureDashboard, getMergedPressureRecords } from '@/actions/pressure'
import type { DashboardStats, MergedPressureRow } from '@/types/pressure'

const { Title, Text } = Typography

const menuItems = [
  {
    key: '/production/pressure/records',
    title: '数据记录',
    description: '压差记录查看、筛选、导出',
    icon: <UnorderedListOutlined />,
    color: '#5645d4',
  },
  {
    key: '/production/pressure/manual-input',
    title: '手动录入',
    description: '矩阵表格批量录入压差',
    icon: <FormOutlined />,
    color: '#1aae39',
  },
  {
    key: '/production/pressure/ocr-input',
    title: 'OCR 识别',
    description: '拍照识别纸质记录',
    icon: <CameraOutlined />,
    color: '#dd5b00',
  },
  {
    key: '/production/pressure/point-management',
    title: '位点管理',
    description: '维护位点编号与区域',
    icon: <EnvironmentOutlined />,
    color: '#e03131',
  },
  {
    key: '/production/pressure/audit',
    title: '审核管理',
    description: '审核/驳回压差记录',
    icon: <AuditOutlined />,
    color: '#8b5cf6',
  },

]
export default function PressureDashboard() {
  const router = useRouter()
  const [stats, setStats] = useState<DashboardStats>({
    today_count: 0,
    pending_count: 0,
    last_record_time: null,
  })
  const [recentRecords, setRecentRecords] = useState<MergedPressureRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/immutability
    loadData()
  }, [])

  const loadData = async () => {
    try {
      const [statsRes, recordsRes] = await Promise.all([
        getPressureDashboard(),
        getMergedPressureRecords({ page: 1, page_size: 5 }),
      ])
      if (statsRes.code === 200) {
        setStats(statsRes.data)
      }
      if (recordsRes.code === 200) {
        setRecentRecords(recordsRes.data || [])
      }
    } catch (error) {
      console.error('Failed to load dashboard data:', error)
    } finally {
      setLoading(false)
    }
  }

  const getStatusTag = (status: string) => {
    const map: Record<string, { color: string; label: string }> = {
      pending: { color: 'warning', label: '待审核' },
      approved: { color: 'success', label: '已通过' },
      rejected: { color: 'error', label: '已驳回' },
    }
    const config = map[status] || { color: 'default', label: status }
    return <Tag color={config.color}>{config.label}</Tag>
  }

  const recentColumns: ColumnsType<MergedPressureRow> = [
    {
      title: '位点编号',
      dataIndex: 'point_id',
      key: 'point_id',
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '区域',
      dataIndex: 'area',
      key: 'area',
    },
    {
      title: '日期',
      dataIndex: 'date',
      key: 'date',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => getStatusTag(status),
    },
  ]

  return (
    <div className="space-y-6">
      <div>
        <Title level={4} className="mb-1">压差统计</Title>
        <Text type="secondary">车间压差巡检记录管理</Text>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Spin size="large" />
        </div>
      ) : (
        <>
          <Row gutter={16}>
            <Col span={8}>
              <Card variant="borderless" className="shadow-sm">
                <Statistic
                  title="今日记录"
                  value={stats.today_count}
                  styles={{ content: { color: '#5645d4' } }}
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card variant="borderless" className="shadow-sm">
                <Statistic
                  title="待审核"
                  value={stats.pending_count}
                  styles={{ content: { color: '#dd5b00' } }}
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card variant="borderless" className="shadow-sm">
                <Statistic
                  title="最后记录时间"
                  value={
                    stats.last_record_time
                      ? new Date(stats.last_record_time).toLocaleString('zh-CN')
                      : '暂无'
                  }
                  styles={{ content: { fontSize: 16 } }}
                />
              </Card>
            </Col>
          </Row>

          <Row gutter={24}>
            <Col span={14}>
              <Card title="快速入口" variant="borderless" className="shadow-sm h-full">
                <Row gutter={[16, 16]}>
                  {menuItems.map((item) => (
                    <Col span={12} key={item.key}>
                      <div
                        className="p-4 rounded-lg border border-[var(--color-hairline)] hover:border-[var(--color-primary)] cursor-pointer transition-colors"
                        onClick={() => router.push(item.key)}
                      >
                        <Space align="start">
                          <div
                            className="w-10 h-10 rounded-lg flex items-center justify-center text-white text-lg"
                            style={{ backgroundColor: item.color }}
                          >
                            {item.icon}
                          </div>
                          <div>
                            <Text strong className="block">{item.title}</Text>
                            <Text type="secondary" className="text-xs">
                              {item.description}
                            </Text>
                          </div>
                          <ArrowRightOutlined className="text-[var(--color-muted)] ml-auto" />
                        </Space>
                      </div>
                    </Col>
                  ))}
                </Row>
              </Card>
            </Col>

            <Col span={10}>
              <Card
                title="最近记录"
                variant="borderless"
                className="shadow-sm h-full"
                extra={
                  <a onClick={() => router.push('/production/pressure/records')}>
                    查看全部
                  </a>
                }
              >
                {recentRecords.length > 0 ? (
                  <Table
                    columns={recentColumns}
                    dataSource={recentRecords}
                    rowKey={(r) => `${r.point_id}-${r.date}`}
                    size="small"
                    pagination={false}
                    className="cursor-pointer"
                    onRow={(record) => ({
                      onClick: () =>
                        router.push('/production/pressure/records'),
                    })}
                  />
                ) : (
                  <div className="text-center py-8 text-[var(--color-muted)]">
                    暂无记录数据
                  </div>
                )}
              </Card>
            </Col>
          </Row>
        </>
      )}
    </div>
  )
}
