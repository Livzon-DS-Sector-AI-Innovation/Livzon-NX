'use client'
// DR 多拉菌素 — 通用台账表格组件（带列定义 + 单元格合并）

import { useEffect, useMemo, useState } from 'react'
import { Table, Card, Typography, Button, Space, Pagination, App } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'

const { Title, Text } = Typography
const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

interface ColDef { title: string; dataIndex: string; width?: number; ellipsis?: boolean; render?: (v: any) => string }

interface Props {
  tableKey: string
  title: string
  columns: ColDef[]
  stages: { key: string; label: string; path: string; active?: boolean }[]
  /** 按哪些列分组合并（如 ["发酵液批号","生产日期"]），相邻行这些列全相同时合并 */
  mergeKeys?: string[]
}

export default function DRTablePage({ tableKey, title, columns: columnDefs, stages, mergeKeys }: Props) {
  const router = useRouter()
  const { message } = App.useApp()
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const load = async (p = 1, ps = 20) => {
    setLoading(true)
    try {
      const r = await fetch(`${API}/api/v1/production/dr/records?table=${tableKey}&page=${p}&page_size=${ps}`)
      const json = await r.json()
      if (json.code === 200) {
        const items = json.data.items || []
        console.log('[DRTablePage] API 返回:', { total: json.data.total, count: items.length })
        if (items.length > 0) {
          console.log('[DRTablePage] 第一条数据 keys:', Object.keys(items[0]))
          console.log('[DRTablePage] 第一条数据:', JSON.stringify(items[0], null, 2))
        }
        setData(items)
        setTotal(json.data.total || 0)
      } else message.error(json.message || '加载失败')
    } catch { message.error('网络错误') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  // ── 合并单元格：相邻行 mergeKeys 全相同时，第一行 rowSpan=组大小，其余为 0 ──
  const computedData = useMemo(() => {
    const result = data.map((row) => ({ ...row }))
    if (!mergeKeys || mergeKeys.length === 0) return result

    // 扫描分组
    let groupStart = 0
    while (groupStart < result.length) {
      let groupEnd = groupStart + 1
      while (groupEnd < result.length) {
        const same = mergeKeys.every(k => result[groupEnd][k] === result[groupStart][k])
        if (same) groupEnd++
        else break
      }
      const span = groupEnd - groupStart
      result[groupStart]._rowSpan = span
      for (let i = groupStart + 1; i < groupEnd; i++) {
        result[i]._rowSpan = 0
      }
      groupStart = groupEnd
    }
    return result
  }, [data, mergeKeys])

  // 生成 onCell —— 只对 mergeKeys 中的列生效
  const mergeKeysSet = useMemo(() => new Set(mergeKeys || []), [mergeKeys])
  const onCellByCol = useMemo(() => {
    const map: Record<string, (record: any) => { rowSpan: number }> = {}
    if (mergeKeys) {
      for (const k of mergeKeys) {
        map[k] = (record: any) => ({ rowSpan: record._rowSpan ?? 1 })
      }
    }
    return map
  }, [mergeKeys])

  const tableCols = columnDefs.map(c => {
    const col = {
      ...c,
      ellipsis: c.ellipsis !== false && !c.title.includes('\n'),
      render: c.render || ((v: any) => v != null ? String(v) : '-'),
      onCell: mergeKeysSet.has(c.dataIndex) ? onCellByCol[c.dataIndex] : undefined,
    }
    return col
  })

  // 调试：打印列定义
  useEffect(() => {
    if (data.length > 0) {
      console.log('[DRTablePage] 列 dataIndex:', columnDefs.map(c => c.dataIndex))
      console.log('[DRTablePage] computedData[0]:', JSON.stringify(computedData[0], null, 2))
      console.log('[DRTablePage] tableCols[0]:', JSON.stringify(tableCols[0]))
    }
  }, [data, columnDefs, computedData, tableCols])

  return (
    <div className="p-6">
      <Card size="small" className="mb-4">
        <Space wrap>{stages.map(s => (
          <Button key={s.key} type={s.active ? 'primary' : 'default'} size="small" onClick={() => router.push(s.path)}>{s.label}</Button>
        ))}</Space>
      </Card>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => router.push('/production/batches/workshop/201-3')}>返回车间</Button>
          {title}
        </Title>
        <Text type="secondary">共 {total} 条</Text>
      </div>

      <Card>
        <Table dataSource={computedData.map((r, i) => ({ ...r, key: r.id || i }))} columns={tableCols}
          loading={loading} size="small" scroll={{ x: columnDefs.length * 110 }} pagination={false} />
        <div style={{ marginTop: 12, textAlign: 'right' }}>
          <Pagination total={total} current={page} pageSize={pageSize}
            showTotal={(t) => `共 ${t} 条`} showSizeChanger
            pageSizeOptions={['10', '20', '50', '100']}
            onChange={(p, ps) => { if (ps !== pageSize) p = 1; setPage(p); setPageSize(ps); load(p, ps) }} />
        </div>
      </Card>
    </div>
  )
}
