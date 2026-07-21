'use client'

import { useMemo, useState } from 'react'
import { Card, Col, Input, Row, Select, Space, Statistic, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import type { RawMaterial } from '@/types/warehouse'

const { Search } = Input

interface RawMaterialTableProps {
  initialItems: RawMaterial[]
}

function formatNumber(value: number | null | undefined): string {
  return Number(value || 0).toLocaleString('zh-CN', {
    maximumFractionDigits: 2,
  })
}

export function RawMaterialTable({ initialItems }: RawMaterialTableProps) {
  const [search, setSearch] = useState('')
  const [productFilter, setProductFilter] = useState<string>('')

  const productLines = useMemo(() => {
    const values = new Set(
      initialItems.map((item) => item.product_line).filter(Boolean),
    )
    return Array.from(values).sort()
  }, [initialItems])

  const filteredData = useMemo(() => {
    let data = initialItems.filter(
      (item) =>
        Number(item.available || 0) > 0 ||
        Number(item.safety || 0) > 0 ||
        Number(item.this_month_use || 0) > 0,
    )

    if (search) {
      const keyword = search.toLowerCase()
      data = data.filter(
        (item) =>
          item.name.toLowerCase().includes(keyword) ||
          item.code.toLowerCase().includes(keyword) ||
          (item.product_line || '').toLowerCase().includes(keyword),
      )
    }

    if (productFilter) {
      data = data.filter((item) => item.product_line === productFilter)
    }

    return data
  }, [initialItems, productFilter, search])

  const stats = useMemo(() => {
    const warningCount = filteredData.filter((item) =>
      item.warning?.includes('不足'),
    ).length
    const criticalCount = filteredData.filter((item) =>
      item.warning?.includes('严重'),
    ).length
    return { total: filteredData.length, warningCount, criticalCount }
  }, [filteredData])

  const columns: ColumnsType<RawMaterial> = [
    {
      title: '物料编码',
      dataIndex: 'code',
      key: 'code',
      width: 110,
      fixed: 'left',
    },
    {
      title: '物料名称',
      dataIndex: 'name',
      key: 'name',
      width: 180,
      fixed: 'left',
      render: (text: string) => (
        <span className="font-medium text-[var(--color-charcoal)]">{text}</span>
      ),
    },
    { title: '规格', dataIndex: 'spec', key: 'spec', width: 140 },
    {
      title: '产品线',
      dataIndex: 'product_line',
      key: 'product_line',
      width: 100,
      render: (value?: string | null) => (value ? <Tag>{value}</Tag> : '-'),
    },
    {
      title: '可用库存',
      dataIndex: 'available',
      key: 'available',
      width: 110,
      sorter: (a, b) => Number(a.available || 0) - Number(b.available || 0),
      render: formatNumber,
    },
    {
      title: '安全库存',
      dataIndex: 'safety',
      key: 'safety',
      width: 110,
      render: formatNumber,
    },
    {
      title: '上月库存',
      dataIndex: 'last_month',
      key: 'last_month',
      width: 110,
      render: formatNumber,
    },
    {
      title: '本月用量',
      dataIndex: 'this_month_use',
      key: 'this_month_use',
      width: 110,
      sorter: (a, b) =>
        Number(a.this_month_use || 0) - Number(b.this_month_use || 0),
      render: formatNumber,
    },
    {
      title: '今日结存',
      dataIndex: 'today_balance',
      key: 'today_balance',
      width: 110,
      render: formatNumber,
    },
    {
      title: '预警',
      dataIndex: 'warning',
      key: 'warning',
      width: 140,
      render: (value?: string | null) => {
        if (!value) return <span className="text-[var(--color-muted)]">正常</span>
        if (value.includes('严重')) return <Tag color="error">{value}</Tag>
        if (value.includes('不足')) return <Tag color="warning">{value}</Tag>
        return <Tag>{value}</Tag>
      },
    },
  ]

  return (
    <div>
      <Row gutter={[16, 16]} className="mb-6">
        <Col xs={24} md={8}>
          <Card variant="borderless">
            <Statistic title="原辅料品种数" value={stats.total} suffix="种" />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card variant="borderless">
            <Statistic
              title="库存不足"
              value={stats.warningCount}
              suffix="种"
              styles={{
                content: {
                  color: stats.warningCount > 0 ? '#dd5b00' : undefined,
                },
              }}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card variant="borderless">
            <Statistic
              title="严重不足"
              value={stats.criticalCount}
              suffix="种"
              styles={{
                content: {
                  color: stats.criticalCount > 0 ? '#e03131' : undefined,
                },
              }}
            />
          </Card>
        </Col>
      </Row>

      <Card variant="borderless">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)]">
            原辅料库存明细
          </h2>
          <Space wrap>
            <Select
              placeholder="产品线"
              allowClear
              style={{ width: 140 }}
              value={productFilter || undefined}
              onChange={(value) => setProductFilter(value || '')}
              options={productLines.map((value) => ({ label: value, value }))}
            />
            <Search
              placeholder="搜索物料名称/编码"
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
          scroll={{ x: 1230 }}
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
        />
      </Card>
    </div>
  )
}
