'use client'
// DR 201三车间 — 一次精制岗位台账

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { Card, Button, Space, Spin, Typography, App, Select } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import DRRefinementTable from '@/components/production/DRRefinementTable'
import DRTraceButton from '@/components/production/DRTraceButton'

const { Title, Text } = Typography
const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

const STAGES = [
  { key: 'crude', label: '过滤萃取', path: '/production/batches/workshop/201-3/crude-extraction' },
  { key: 'chromatography', label: '层析及一次结晶岗位', path: '/production/batches/workshop/201-3/extraction' },
  { key: 'refine1', label: '一次精制', path: '/production/batches/workshop/201-3/dr-refinement', active: true },
  { key: 'refine2', label: '二次精制', path: '/production/batches/workshop/201-3/blending' },
  { key: 'refine3', label: '三次精制', path: '/production/batches/workshop/201-3/qc-inspection' },
  { key: 'refine4', label: '四次精品', path: '/production/batches/workshop/201-3/butyl-acetate' },
]

export default function DrRefinementPage() {
  const router = useRouter()
  const { message } = App.useApp()
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [year, setYear] = useState<number>(0)   // 0 = 全部
  const [month, setMonth] = useState<number>(0) // 0 = 全部
  const [years, setYears] = useState<number[]>([])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      // 一次性拉全量（筛选后最多数百行），合并单元格依赖整批数据计算 rowSpan
      const params = new URLSearchParams()
      params.set('table', 'dr_first_refinement')
      params.set('page', '1')
      params.set('page_size', '5000')
      if (year > 0) params.set('year', String(year))
      if (month > 0) params.set('month', String(month))
      const r = await fetch(`${API}/api/v1/production/dr/records?${params}`)
      const json = await r.json()
      if (json.code === 200) setData(json.data?.items || [])
      else message.error(json.message || '加载失败')
    } catch {
      message.error('网络错误')
    } finally {
      setLoading(false)
    }
  }, [year, month])

  useEffect(() => { loadData() }, [loadData])

  // 初次加载可用年份列表，数据更新到新年份时下拉框自动跟随
  useEffect(() => {
    fetch(`${API}/api/v1/production/dr/records/years?table=dr_first_refinement`)
      .then(r => r.json())
      .then(json => { if (json.code === 200) setYears(json.data || []) })
      .catch(() => {})
  }, [])

  const yearOptions = useMemo(() => [
    { value: 0, label: '全部' },
    ...years.map(y => ({ value: y, label: `${y}年` })),
  ], [years])
  const monthOptions = useMemo(() => [
    { value: 0, label: '全部' },
    ...[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(m => ({ value: m, label: `${m}月` })),
  ], [])

  return (
    <div className="p-6">
      {/* 工段导航 */}
      <Card size="small" className="mb-4">
        <Space wrap>
          {STAGES.map(s => (
            <Button key={s.key} type={s.active ? 'primary' : 'default'} size="small" onClick={() => router.push(s.path)}>
              {s.label}
            </Button>
          ))}
        </Space>
      </Card>

      {/* 标题栏 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => router.push('/production/batches/workshop/201-3')}>
            返回车间
          </Button>
          一次精制台账
        </Title>
        <Space size={8}>
          <Select size="small" style={{ width: 80 }} value={year} onChange={v => setYear(v)} options={yearOptions} />
          <Select size="small" style={{ width: 80 }} value={month} onChange={v => setMonth(v)} options={monthOptions} />
          <Text type="secondary">共 {data.length} 条</Text>
          <DRTraceButton initialModule="first_refinement" />
        </Space>
      </div>

      {/* 表格 */}
      <Card>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '80px 0' }}>
            <Spin size="large" />
          </div>
        ) : (
          <DRRefinementTable data={data} />
        )}
      </Card>
    </div>
  )
}
