'use client'

import { Table } from 'antd'
import Alert from '@/components/shared/PlatformNotice'
import { WarningOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { StockWarning } from '@/types/equipment'

export function StockWarningTable({
  warnings,
  loading = false,
}: {
  warnings: StockWarning[]
  loading?: boolean
}) {

  const columns: ColumnsType<StockWarning> = [
    {
      title: '编码', key: 'code', width: 120,
      render: (_: unknown, record: StockWarning) => record.spare_part.code,
    },
    {
      title: '名称', key: 'name', width: 150,
      render: (_: unknown, record: StockWarning) => record.spare_part.name,
    },
    {
      title: '当前库存', key: 'current_qty', width: 100, align: 'right',
      render: (_: unknown, record: StockWarning) => (
        <span style={{ color: 'var(--color-error)', fontWeight: 600 }}>{record.stock.current_qty}</span>
      ),
    },
    {
      title: '安全库存', key: 'safety_qty', width: 100, align: 'right',
      render: (_: unknown, record: StockWarning) => record.stock.safety_qty,
    },
    {
      title: '差额', key: 'shortage', width: 100, align: 'right',
      render: (_: unknown, record: StockWarning) => (
        <span style={{ color: 'var(--color-error)', fontWeight: 600 }}>{record.shortage}</span>
      ),
    },
  ]

  return (
    <div>
      {warnings.length > 0 && (
        <Alert
          title={`${warnings.length} 个备件库存低于安全库存，请及时补充`}
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: 16 }}
        />
      )}
      <Table
        columns={columns} dataSource={warnings} rowKey={(r) => r.spare_part.id} size="small" loading={loading}
        scroll={{ x: 'max-content' }}
        pagination={false}
      />
    </div>
  )
}
