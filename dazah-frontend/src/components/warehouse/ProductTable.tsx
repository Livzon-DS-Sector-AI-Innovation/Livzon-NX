'use client'

import { useMemo, useState } from 'react'
import { Card, Col, Input, Progress, Row, Space, Statistic, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import type { ProductInventory } from '@/types/warehouse'

const { Search } = Input

interface ProductTableProps {
  initialItems: ProductInventory[]
}

function formatNumber(value: number | null | undefined): string {
  return Number(value || 0).toLocaleString('zh-CN', {
    maximumFractionDigits: 2,
  })
}

export function ProductTable({ initialItems }: ProductTableProps) {
  const [search, setSearch] = useState('')

  const filteredData = useMemo(() => {
    if (!search) return initialItems

    const keyword = search.toLowerCase()
    return initialItems.filter((item) =>
      item.name.toLowerCase().includes(keyword),
    )
  }, [initialItems, search])

  const stats = useMemo(() => {
    const totalQualified = filteredData.reduce(
      (sum, item) => sum + Number(item.qualified_quantity || 0),
      0,
    )
    const totalRemaining = filteredData.reduce(
      (sum, item) => sum + Number(item.remaining_quantity || 0),
      0,
    )
    return {
      totalProducts: filteredData.length,
      totalQualified,
      totalRemaining,
    }
  }, [filteredData])

  const columns: ColumnsType<ProductInventory> = [
    {
      title: '产品名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      fixed: 'left',
      render: (text: string) => (
        <span className="font-medium text-[var(--color-charcoal)]">{text}</span>
      ),
    },
    { title: '规格', dataIndex: 'spec', key: 'spec', width: 150 },
    {
      title: '单位',
      dataIndex: 'unit',
      key: 'unit',
      width: 80,
      render: (value?: string | null) => (value ? <Tag>{value}</Tag> : '-'),
    },
    {
      title: '订单量',
      dataIndex: 'order_quantity',
      key: 'order_quantity',
      width: 110,
      sorter: (a, b) =>
        Number(a.order_quantity || 0) - Number(b.order_quantity || 0),
      render: formatNumber,
    },
    {
      title: '待检',
      dataIndex: 'pending_quantity',
      key: 'pending_quantity',
      width: 100,
      render: formatNumber,
    },
    {
      title: '合格数量',
      dataIndex: 'qualified_quantity',
      key: 'qualified_quantity',
      width: 110,
      render: formatNumber,
    },
    {
      title: '小计',
      dataIndex: 'subtotal_quantity',
      key: 'subtotal_quantity',
      width: 110,
      render: formatNumber,
    },
    {
      title: '剩余量',
      dataIndex: 'remaining_quantity',
      key: 'remaining_quantity',
      width: 110,
      render: formatNumber,
    },
    {
      title: '完成率',
      key: 'rate',
      width: 160,
      render: (_, record) => {
        if (!record.order_quantity) return '-'

        const rate = Math.min(
          100,
          Math.round(
            (Number(record.qualified_quantity || 0) /
              Number(record.order_quantity || 1)) *
              100,
          ),
        )
        const color = rate >= 80 ? '#1aae39' : rate >= 50 ? '#dd5b00' : '#e03131'
        return <Progress percent={rate} size="small" strokeColor={color} />
      },
    },
  ]

  return (
    <div>
      <Row gutter={[16, 16]} className="mb-6">
        <Col xs={24} md={8}>
          <Card variant="borderless">
            <Statistic title="产品品种" value={stats.totalProducts} suffix="种" />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card variant="borderless">
            <Statistic title="合格总量" value={formatNumber(stats.totalQualified)} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card variant="borderless">
            <Statistic title="剩余量" value={formatNumber(stats.totalRemaining)} />
          </Card>
        </Col>
      </Row>

      <Card variant="borderless">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)]">
            成品库存明细
          </h2>
          <Space wrap>
            <Search
              placeholder="搜索产品名称"
              onSearch={setSearch}
              onChange={(event) => !event.target.value && setSearch('')}
              style={{ width: 240 }}
              allowClear
            />
          </Space>
        </div>
        <Table
          columns={columns}
          dataSource={filteredData}
          rowKey="id"
          size="small"
          scroll={{ x: 1130 }}
          pagination={{
            pageSize: 20,
            showTotal: (total) => `共 ${total} 条`,
          }}
        />
      </Card>
    </div>
  )
}
