'use client'
import { useEffect, useState, useMemo } from 'react'
import { Table, Card, Typography, Button, App, Space } from 'antd'
import {ArrowLeftOutlined,} from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import MCSheetsSyncButton from '@/components/production/MCSheetsSyncButton'
const { Title, Text } = Typography

export default function ButylAcetatePage() {
  const router = useRouter()
  const { message } = App.useApp()
  const [data, setData] = useState<{
    dates: string[]; equipment: string[]; matrix: Record<string, Record<string, number | null>>;
    inbound: Record<string, number | null>; checks: Record<string, number | null>
  } | null>(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/v1/production/mc/ba-records')
      const json = await res.json()
      if (json.code === 200) setData(json.data)
    } catch { message.error('加载失败') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])
  const [now, setNow] = useState('')
  useEffect(() => {
    setNow(new Date().toLocaleString('zh-CN'))
    const t = setInterval(() => setNow(new Date().toLocaleString('zh-CN')), 1000)
    return () => clearInterval(t)
  }, [])

  const columns = useMemo(() => {
    if (!data) return []
    const cols: any[] = [
      { title: '设备', dataIndex: 'equipment', fixed: 'left' as const, width: 140,
        render: (v: string) => <Text strong>{v}</Text> },
    ]
    for (const d of data.dates) {
      const label = d.slice(5) // MM-DD
      cols.push({
        title: label, dataIndex: d, width: 80, align: 'right' as const,
        render: (v: number | null | undefined) =>
          v != null ? <Text style={{ color: v === 0 ? '#ccc' : undefined }}>{v.toFixed(v < 10 ? 2 : 0)}</Text> : <Text type="secondary">—</Text>,
      })
    }
    return cols
  }, [data])

  const tableData = useMemo(() => {
    if (!data) return []
    return data.equipment.map(eq => {
      const row: any = { key: eq, equipment: eq }
      for (const d of data.dates) row[d] = data.matrix[eq]?.[d] ?? null
      return row
    })
  }, [data])

  // 入库行
  const inboundRow = useMemo(() => {
    if (!data) return null
    const row: any = { key: '__inbound__', equipment: '📥 入库(m³)' }
    for (const d of data.dates) row[d] = data.inbound[d] ?? null
    return row
  }, [data])

  return <div className="p-6">
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
      <Title level={4} style={{ margin: 0 }}>
        <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => router.push('/production/batches/workshop/201-2')}>返回车间</Button>
        乙酸丁酯台账
      </Title>
      <Space>
        <MCSheetsSyncButton />
      </Space>
    </div>

    {/* 库存卡片 */}
    {data?.checks && Object.keys(data.checks).length > 0 && (() => {
      const checkEntries = Object.entries(data.checks).filter(([, v]) => v != null) as [string, number][]
      if (checkEntries.length === 0) return null
      const last = checkEntries[checkEntries.length - 1]
      return (
        <Card size="small" className="mb-4" title={
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>库存（截止 {last[0].slice(5)}）</span>
            <Text type="secondary" style={{ fontWeight: 400 }}>{now}</Text>
          </div>
        }>
          <Text strong style={{ fontSize: 24, color: '#1677ff' }}>{last[1]} 吨</Text>
          <div style={{ marginTop: 8, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {checkEntries.slice(0, -1).map(([d, v]) => (
              <Text key={d} type="secondary">{d.slice(5)}: {v} 吨</Text>
            ))}
          </div>
        </Card>
      )
    })()}

    {/* 入库卡片 */}
    {data?.inbound && Object.keys(data.inbound).length > 0 && (
      <Card size="small" className="mb-4" title="入库记录">
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {Object.entries(data.inbound).map(([d, v]) => (
            <div key={d} style={{ background: '#f6ffed', padding: '8px 16px', borderRadius: 6, border: '1px solid #b7eb8f' }}>
              <Text type="secondary">{d.slice(5)}</Text>
              <div><Text strong style={{ fontSize: 18, color: '#52c41a' }}>{v} m³</Text></div>
            </div>
          ))}
        </div>
      </Card>
    )}

    {/* 消耗交叉表 */}
    <Card title={`消耗明细 · ${data?.dates?.length || 0}个盘点日期 · ${data?.equipment?.length || 0}台设备`}>
      <Table
        columns={columns}
        dataSource={inboundRow ? [...tableData, inboundRow] : tableData}
        loading={loading}
        size="small"
        scroll={{ x: 'max-content' }}
        pagination={false}
        bordered
      />
    </Card>
  </div>
}
