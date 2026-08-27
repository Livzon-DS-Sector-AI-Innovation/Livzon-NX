'use client'

import { useState, useMemo } from 'react'
import { Table, Input, Tag, Statistic, Card, Row, Col, Select, Space } from 'antd'
import type { PackagingMaterial } from '@/types/warehouse'

const { Search } = Input

interface PackagingTableProps {
  initialItems: PackagingMaterial[]
}

export function PackagingTable({ initialItems }: PackagingTableProps) {
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>('')

  const categories = useMemo(() => {
    const cats = new Set(initialItems.map(m => m.product).filter(Boolean))
    return Array.from(cats).sort()
  }, [initialItems])

  const filteredData = useMemo(() => {
    let data = initialItems.filter(m => m.available > 0 || m.safety > 0 || m.thisMonthUse > 0)
    if (search) {
      const s = search.toLowerCase()
      data = data.filter(m =>
        m.name.toLowerCase().includes(s) ||
        m.code.toLowerCase().includes(s)
      )
    }
    if (categoryFilter) {
      data = data.filter(m => m.product === categoryFilter)
    }
    return data
  }, [categoryFilter, initialItems, search])

  const stats = useMemo(() => {
    const total = filteredData.length
    const warningCount = filteredData.filter(m => m.warning && m.warning.includes('不足')).length
    return { total, warningCount }
  }, [filteredData])

  const columns = [
    { title: '编码', dataIndex: 'code', key: 'code', width: 90, fixed: 'left' as const },
    {
      title: '名称', dataIndex: 'name', key: 'name', width: 150, fixed: 'left' as const,
      render: (text: string) => <span className="font-medium text-[var(--color-charcoal)]">{text}</span>,
    },
    { title: '规格', dataIndex: 'spec', key: 'spec', width: 120 },
    { title: '批次', dataIndex: 'batch', key: 'batch', width: 100 },
    { title: '产品线', dataIndex: 'product', key: 'product', width: 70, render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
    { title: '可用库存', dataIndex: 'available', key: 'available', width: 100, sorter: (a: PackagingMaterial, b: PackagingMaterial) => a.available - b.available, render: (v: number) => v.toLocaleString() },
    { title: '安全库存', dataIndex: 'safety', key: 'safety', width: 100, render: (v: number) => v.toLocaleString() },
    { title: '本月用量', dataIndex: 'thisMonthUse', key: 'thisMonthUse', width: 100, sorter: (a: PackagingMaterial, b: PackagingMaterial) => a.thisMonthUse - b.thisMonthUse, render: (v: number) => v.toLocaleString() },
    { title: '今日结存', dataIndex: 'todayBalance', key: 'todayBalance', width: 100, render: (v: number) => v.toLocaleString() },
    {
      title: '预警', dataIndex: 'warning', key: 'warning', width: 120,
      render: (val: string) => {
        if (!val) return <span className="text-[var(--color-muted)]">正常</span>
        if (val.includes('严重')) return <Tag color="error">{val}</Tag>
        if (val.includes('不足')) return <Tag color="warning">{val}</Tag>
        return <Tag>{val}</Tag>
      },
    },
  ]

  return (
    <div>
      <Row gutter={16} className="mb-6">
        <Col span={12}>
          <Card variant="borderless">
            <Statistic title="包材品种数" value={stats.total} suffix="种" />
          </Card>
        </Col>
        <Col span={12}>
          <Card variant="borderless">
            <Statistic
              title="库存不足"
              value={stats.warningCount}
              suffix="种"
              styles={{ content: { color: stats.warningCount > 0 ? '#dd5b00' : undefined } }}
            />
          </Card>
        </Col>
      </Row>

      <Card variant="borderless">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[16px] font-semibold text-[var(--color-charcoal)]">包材库存明细</h3>
          <Space>
            <Select placeholder="产品线" allowClear style={{ width: 120 }} value={categoryFilter || undefined} onChange={(v) => setCategoryFilter(v || '')} options={categories.map(c => ({ label: c, value: c }))} />
            <Search placeholder="搜索名称/编码" onSearch={setSearch} onChange={(e) => !e.target.value && setSearch('')} style={{ width: 220 }} allowClear />
          </Space>
        </div>
        <Table columns={columns} dataSource={filteredData} rowKey="id" size="small" scroll={{ x: 1100 }} pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }} />
      </Card>
    </div>
  )
}
