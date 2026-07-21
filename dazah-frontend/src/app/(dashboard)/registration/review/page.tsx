'use client'

"use client"

'use client'

import { useEffect, useState, useCallback } from 'react'
import {
  Table, Button, Space, Tag, Input, Select, Modal, App, Form, DatePicker,
  Statistic, Row, Col, Card, Timeline, Popconfirm, Drawer,
  Segmented, Empty, Spin,
} from 'antd'
import {
  PlusOutlined, SearchOutlined, ReloadOutlined, DeleteOutlined,
  EditOutlined, BarChartOutlined, BarsOutlined,
} from '@ant-design/icons'
import dayjs, { Dayjs } from 'dayjs'
import {
  Drug, DrugCreate, DrugUpdate, ReviewNodeConfig,
  fetchDrugs, fetchReviewNodes, createDrug, updateDrug, deleteDrug,
} from '@/lib/api/registration-client'

type ViewMode = 'list' | 'gantt'
type DrugType = '仿制药' | '创新药' | '原料药'

const TYPE_COLORS: Record<DrugType, string> = {
  '创新药': 'purple',
  '仿制药': 'blue',
  '原料药': 'green',
}

const STATUS_COLORS: Record<string, string> = {
  completed: 'green',
  'in-progress': 'blue',
  pending: 'default',
}

const DEFAULT_HOLIDAYS_2025 = [
  '2025-01-01','2025-01-28','2025-01-29','2025-01-30','2025-01-31',
  '2025-02-01','2025-02-02','2025-02-03','2025-02-04',
  '2025-04-04','2025-04-05','2025-04-06',
  '2025-05-01','2025-05-02','2025-05-03','2025-05-04','2025-05-05',
  '2025-05-31','2025-06-01','2025-06-02',
  '2025-10-01','2025-10-02','2025-10-03','2025-10-04','2025-10-05',
  '2025-10-06','2025-10-07','2025-10-08',
]
const DEFAULT_HOLIDAYS_2026 = [
  '2026-01-01','2026-01-02','2026-01-03',
  '2026-02-15','2026-02-16','2026-02-17','2026-02-18','2026-02-19',
  '2026-02-20','2026-02-21','2026-02-22','2026-02-23',
  '2026-04-04','2026-04-05','2026-04-06',
  '2026-05-01','2026-05-02','2026-05-03','2026-05-04','2026-05-05',
  '2026-06-19','2026-06-20','2026-06-21',
  '2026-09-25','2026-09-26','2026-09-27',
  '2026-10-01','2026-10-02','2026-10-03','2026-10-04','2026-10-05',
  '2026-10-06','2026-10-07',
]
const DEFAULT_WORKDAYS_2025 = ['2025-01-26','2025-02-08','2025-04-27','2025-09-28','2025-10-11']
const DEFAULT_WORKDAYS_2026 = ['2026-01-04','2026-02-14','2026-02-28','2026-05-09','2026-09-20','2026-10-10']

function addWorkDays(startStr: string, days: number, holidays: string[], workdays: string[]): string {
  const d = new Date(startStr + 'T00:00:00')
  let remaining = days
  let iterations = 0
  while (remaining > 0) {
    d.setDate(d.getDate() + 1)
    const dateStr = d.toISOString().split('T')[0]
    const dow = d.getDay()
    if (workdays.includes(dateStr)) { remaining--; continue }
    if (dow === 0 || dow === 6) continue
    if (holidays.includes(dateStr)) continue
    remaining--
    iterations++
    if (iterations > 365 * 3) break
  }
  return d.toISOString().split('T')[0]
}

export default function ReviewPage() {
  const [drugs, setDrugs] = useState<Drug[]>([])
  const { message } = App.useApp()
  const [reviewNodes, setReviewNodes] = useState<ReviewNodeConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<string>('全部')
  const [yearFilter, setYearFilter] = useState<string>('全部')
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [selectedDrug, setSelectedDrug] = useState<Drug | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  const holidays = [...DEFAULT_HOLIDAYS_2025, ...DEFAULT_HOLIDAYS_2026]
  const workdays = [...DEFAULT_WORKDAYS_2025, ...DEFAULT_WORKDAYS_2026]

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [d, n] = await Promise.all([fetchDrugs(), fetchReviewNodes()])
      setDrugs(d)
      setReviewNodes(n)
    } catch {
      message.error('加载数据失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const [d, n] = await Promise.all([fetchDrugs(), fetchReviewNodes()])
        if (!cancelled) {
          setDrugs(d)
          setReviewNodes(n)
        }
      } catch {
        if (!cancelled) message.error('加载数据失败')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  const filtered = drugs.filter(d => {
    if (search && !d.name.includes(search)) return false
    if (typeFilter !== '全部' && d.type !== typeFilter) return false
    if (yearFilter !== '全部' && !d.acceptance_date.startsWith(yearFilter)) return false
    return true
  })

  const stats = {
    total: filtered.length,
    firstSubmission: filtered.filter(d => d.type === '创新药').length,
    inProgress: filtered.filter(d => {
      const nodes = d.nodes || []
      const hasCompleted = nodes.some(n => n.actual_date)
      const hasPending = nodes.some(n => !n.actual_date)
      return hasCompleted && hasPending
    }).length,
    approved: filtered.filter(d => {
      const nodes = d.nodes || []
      return nodes.filter(n => n.actual_date).length === 10
    }).length,
  }

  const handleAdd = async (values: { name: string; type: DrugType; acceptance_date: Dayjs }) => {
    setSubmitting(true)
    try {
      await createDrug({
        name: values.name,
        type: values.type,
        acceptance_date: values.acceptance_date.format('YYYY-MM-DD'),
      })
      message.success('添加成功')
      setAddModalOpen(false)
      form.resetFields()
      loadData()
    } catch {
      message.error('添加失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleUpdateNode = async (drugId: string, nodeIndex: number, actualDate: Dayjs | null) => {
    try {
      await updateDrug(drugId, {
        nodes: [{ node_index: nodeIndex, actual_date: actualDate?.format('YYYY-MM-DD') ?? null }],
      })
      message.success('节点更新成功')
      loadData()
    } catch {
      message.error('更新失败')
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteDrug(id)
      message.success('删除成功')
      if (selectedDrug?.id === id) { setSelectedDrug(null); setDrawerOpen(false) }
      loadData()
    } catch {
      message.error('删除失败')
    }
  }

  const openDetail = (drug: Drug) => {
    setSelectedDrug(drug)
    setDrawerOpen(true)
  }

  const getNodeStatus = (drug: Drug, nodeIndex: number): 'completed' | 'in-progress' | 'pending' => {
    const node = drug.nodes?.find(n => n.node_index === nodeIndex)
    if (node?.actual_date) return 'completed'
    const prevNodes = drug.nodes?.filter(n => n.node_index < nodeIndex && n.actual_date) || []
    if (prevNodes.length > 0) return 'in-progress'
    return 'pending'
  }

  const getEstimatedDate = (drug: Drug, nodeIndex: number): string => {
    const startDate = drug.acceptance_date
    let totalDays = 0
    for (const n of reviewNodes) {
      if (n.index <= nodeIndex) totalDays += n.days
    }
    return addWorkDays(startDate, totalDays, holidays, workdays)
  }

  const columns = [
    {
      title: '药品名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: Drug) => (
        <a onClick={() => openDetail(record)}>{text}</a>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type: DrugType) => <Tag color={TYPE_COLORS[type]}>{type}</Tag>,
      width: 100,
    },
    {
      title: '受理日期',
      dataIndex: 'acceptance_date',
      key: 'acceptance_date',
      width: 120,
    },
    {
      title: '当前节点',
      key: 'current_node',
      width: 160,
      render: (_: unknown, record: Drug) => {
        const completedCount = record.nodes?.filter(n => n.actual_date).length || 0
        const nodeConfig = reviewNodes.find(n => n.index === completedCount + 1)
        return (
          <Space>
            <Tag color="blue">{completedCount}/10</Tag>
            {nodeConfig && <span className="text-xs text-gray-500">{nodeConfig.name}</span>}
          </Space>
        )
      },
    },
    {
      title: '预计获批',
      key: 'estimated',
      width: 120,
      render: (_: unknown, record: Drug) => getEstimatedDate(record, 10),
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: unknown, record: Drug) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openDetail(record)}>
            详情
          </Button>
          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.id)} okText="确定" cancelText="取消">
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const ganttData = filtered.map(drug => {
    const items = reviewNodes.map(node => {
      const nodeRecord = drug.nodes?.find(n => n.node_index === node.index)
      const status = getNodeStatus(drug, node.index)
      const startDate = node.index === 1 ? drug.acceptance_date : getEstimatedDate(drug, node.index - 1)
      const endDate = nodeRecord?.actual_date || getEstimatedDate(drug, node.index)
      return { ...node, startDate, endDate, status, actual: nodeRecord?.actual_date || null }
    })
    return { drug, items }
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] m-0">
          申报进度查询
        </h1>
        <Space>
          <Segmented
            value={viewMode}
            onChange={(v) => setViewMode(v as ViewMode)}
            options={[
              { label: <span><BarsOutlined /> 列表</span>, value: 'list' },
              { label: <span><BarChartOutlined /> 甘特图</span>, value: 'gantt' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={loadData} loading={loading}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddModalOpen(true)}>
            添加药品
          </Button>
        </Space>
      </div>

      {/* 统计面板 */}
      <Row gutter={16} className="mb-4">
        <Col span={6}>
          <Card size="small">
            <Statistic title="药品总数" value={stats.total} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="创新药" value={stats.firstSubmission} styles={{ content: { color: '#722ed1' } }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="审评中" value={stats.inProgress} styles={{ content: { color: '#1677ff' } }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="已获批" value={stats.approved} styles={{ content: { color: '#52c41a' } }} />
          </Card>
        </Col>
      </Row>

      {/* 筛选栏 */}
      <Space className="mb-4" wrap>
        <Input
          placeholder="搜索药品名称"
          prefix={<SearchOutlined />}
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ width: 200 }}
          allowClear
        />
        <Select value={typeFilter} onChange={setTypeFilter} style={{ width: 120 }}
          options={[
            { label: '全部类型', value: '全部' },
            { label: '创新药', value: '创新药' },
            { label: '仿制药', value: '仿制药' },
            { label: '原料药', value: '原料药' },
          ]}
        />
        <Select value={yearFilter} onChange={setYearFilter} style={{ width: 120 }}
          options={[
            { label: '全部年份', value: '全部' },
            { label: '2025', value: '2025' },
            { label: '2026', value: '2026' },
            { label: '2027', value: '2027' },
          ]}
        />
      </Space>

      {/* 列表视图 */}
      {viewMode === 'list' && (
        <Table
          dataSource={filtered}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          size="small"
        />
      )}

      {/* 甘特图视图 */}
      {viewMode === 'gantt' && (
        <div className="overflow-x-auto">
          {ganttData.length === 0 ? (
            <Empty description="暂无数据" />
          ) : (
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="bg-gray-50">
                  <th className="border p-2 text-left sticky left-0 bg-gray-50 min-w-[120px]">药品名称</th>
                  {reviewNodes.map(n => (
                    <th key={n.index} className="border p-2 text-center min-w-[100px]">
                      <div className="font-medium">{n.name}</div>
                      <div className="text-gray-400 font-normal">{n.days}天</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ganttData.map(({ drug, items }) => (
                  <tr key={drug.id} className="hover:bg-gray-50">
                    <td className="border p-2 sticky left-0 bg-white">
                      <div className="font-medium">{drug.name}</div>
                      <Tag color={TYPE_COLORS[drug.type as DrugType]} className="mt-1" style={{ fontSize: 10 }}>
                        {drug.type}
                      </Tag>
                    </td>
                    {items.map(item => (
                      <td key={item.index} className="border p-1 text-center">
                        <Tag
                          color={STATUS_COLORS[item.status]}
                          style={{ fontSize: 10, lineHeight: '16px' }}
                        >
                          {item.actual || item.endDate}
                        </Tag>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* 详情抽屉 */}
      <Drawer
        title={selectedDrug?.name}
        open={drawerOpen}
        onClose={() => { setDrawerOpen(false); setSelectedDrug(null) }}
        size="default"
      >
        {selectedDrug && (
          <Spin spinning={loading}>
            <div className="mb-4">
              <Space>
                <Tag color={TYPE_COLORS[selectedDrug.type as DrugType]}>{selectedDrug.type}</Tag>
                <span className="text-gray-500">受理日期：{selectedDrug.acceptance_date}</span>
              </Space>
            </div>
            <Timeline
              items={reviewNodes.map(node => {
                const nodeRecord = selectedDrug.nodes?.find(n => n.node_index === node.index)
                const status = getNodeStatus(selectedDrug, node.index)
                const estimated = getEstimatedDate(selectedDrug, node.index)
                return {
                  key: node.index,
                  color: status === 'completed' ? 'green' : status === 'in-progress' ? 'blue' : 'gray',
                  content: (
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{node.name}</span>
                        <Tag
                          color={STATUS_COLORS[status]}
                          style={{ fontSize: 10 }}
                        >
                          {status === 'completed' ? '已完成' : status === 'in-progress' ? '进行中' : '待处理'}
                        </Tag>
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {nodeRecord?.actual_date ? (
                          <span>实际日期：{nodeRecord.actual_date}</span>
                        ) : (
                          <span>预计日期：{estimated}</span>
                        )}
                        <span className="ml-2">（+{node.days}个工作日）</span>
                      </div>
                      {status !== 'completed' && (
                        <div className="mt-1">
                          <DatePicker
                            size="small"
                            placeholder="标记完成日期"
                            onChange={date => handleUpdateNode(selectedDrug.id, node.index, date)}
                          />
                          {nodeRecord?.actual_date && (
                            <Button size="small" type="link" onClick={() => handleUpdateNode(selectedDrug.id, node.index, null)}>
                              撤销
                            </Button>
                          )}
                        </div>
                      )}
                    </div>
                  ),
                }
              })}
            />
          </Spin>
        )}
      </Drawer>

      {/* 添加药品弹窗 */}
      <Modal
        title="添加药品"
        open={addModalOpen}
        onCancel={() => { setAddModalOpen(false); form.resetFields() }}
        onOk={() => form.submit()}
        confirmLoading={submitting}
      >
        <Form form={form} layout="vertical" onFinish={handleAdd}>
          <Form.Item name="name" label="药品名称" rules={[{ required: true, message: '请输入药品名称' }]}>
            <Input placeholder="请输入药品名称" />
          </Form.Item>
          <Form.Item name="type" label="药品类型" rules={[{ required: true, message: '请选择类型' }]}>
            <Select
              placeholder="请选择类型"
              options={[
                { label: '创新药', value: '创新药' },
                { label: '仿制药', value: '仿制药' },
                { label: '原料药', value: '原料药' },
              ]}
            />
          </Form.Item>
          <Form.Item name="acceptance_date" label="受理日期" rules={[{ required: true, message: '请选择日期' }]}>
            <DatePicker className="w-full" placeholder="请选择受理日期" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
