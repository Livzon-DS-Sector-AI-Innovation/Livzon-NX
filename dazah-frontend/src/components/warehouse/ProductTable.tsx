'use client'

import { useState, useMemo } from 'react'
import { Table, Input, Tag, Statistic, Card, Row, Col, Progress } from 'antd'
import type { ProductInventory } from '@/types/warehouse'

const { Search } = Input

interface ProductTableProps {
  initialItems: ProductInventory[]
}

export function ProductTable({ initialItems }: ProductTableProps) {
  const [search, setSearch] = useState('')

  const filteredData = useMemo(() => {
    if (!search) return initialItems
    const s = search.toLowerCase()
    return initialItems.filter(m => m.name.toLowerCase().includes(s))
  }, [initialItems, search])

  const stats = useMemo(() => {
    const totalProducts = filteredData.length
    const totalQualified = filteredData.reduce((sum, p) => sum + (p.qualified || 0), 0)
    const totalRemaining = filteredData.reduce((sum, p) => sum + (p.remaining || 0), 0)
    return { totalProducts, totalQualified, totalRemaining }
  }, [filteredData])

  const columns = [
    {
      title: '产品名称', dataIndex: 'name', key: 'name', width: 180, fixed: 'left' as const,
      render: (text: string) => <span className="font-medium text-[var(--color-charcoal)]">{text}</span>,
    },
    { title: '规格', dataIndex: 'spec', key: 'spec', width: 120 },
    { title: '单位', dataIndex: 'unit', key: 'unit', width: 60, render: (v: string) => <Tag>{v}</Tag> },
    { title: '订单量', dataIndex: 'orderQty', key: 'orderQty', width: 100, sorter: (a: ProductInventory, b: ProductInventory) => a.orderQty - b.orderQty, render: (v: number) => v.toLocaleString() },
    { title: '待检', dataIndex: 'pending', key: 'pending', width: 80, render: (v: number) => v.toLocaleString() },
    { title: '合格数量', dataIndex: 'qualified', key: 'qualified', width: 100, render: (v: number) => v.toLocaleString() },
    { title: '小计', dataIndex: 'subtotal', key: 'subtotal', width: 100, render: (v: number) => v.toLocaleString() },
    { title: '剩余量', dataIndex: 'remaining', key: 'remaining', width: 100, render: (v: number) => v.toLocaleString() },
    {
      title: '完成率', key: 'rate', width: 150,
      render: (_: unknown, record: ProductInventory) => {
        if (!record.orderQty) return '-'
        const rate = Math.min(100, Math.round((record.qualified / record.orderQty) * 100))
        const color = rate >= 80 ? '#1aae39' : rate >= 50 ? '#dd5b00' : '#e03131'
        return <Progress percent={rate} size="small" strokeColor={color} />
      },
    },
  ]

  return (
    <div>
      <Row gutter={16} className="mb-6">
        <Col span={8}>
          <Card variant="borderless">
            <Statistic title="产品品种" value={stats.totalProducts} suffix="种" />
          </Card>
        </Col>
        <Col span={8}>
          <Card variant="borderless">
            <Statistic title="合格总量" value={stats.totalQualified} />
          </Card>
        </Col>
        <Col span={8}>
          <Card variant="borderless">
            <Statistic title="剩余量" value={stats.totalRemaining} />
          </Card>
        </Col>
      </Row>

      <Card variant="borderless">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[16px] font-semibold text-[var(--color-charcoal)]">成品库存明细</h3>
          <Search placeholder="搜索产品名称" onSearch={setSearch} onChange={(e) => !e.target.value && setSearch('')} style={{ width: 220 }} allowClear />
        </div>
        <Table columns={columns} dataSource={filteredData} rowKey="id" size="small" scroll={{ x: 1000 }} pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }} />
      </Card>
    </div>
  )
}
