'use client'
// DR 201三车间 — 三次精制岗位台账

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { Card, Button, Space, Spin, Typography, App, Select } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { DRRefinementTable } from '@/components/production/DRRefinementTable'
import type { RefineColDef } from '@/components/production/DRRefinementTable'
import DRTraceButton from '@/components/production/DRTraceButton'

const { Title, Text } = Typography
const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

const STAGES = [
  { key: 'crude', label: '过滤萃取', path: '/production/batches/workshop/201-3/crude-extraction' },
  { key: 'chromatography', label: '层析及一次结晶岗位', path: '/production/batches/workshop/201-3/extraction' },
  { key: 'refine1', label: '一次精制', path: '/production/batches/workshop/201-3/dr-refinement' },
  { key: 'refine2', label: '二次精制', path: '/production/batches/workshop/201-3/blending' },
  { key: 'refine3', label: '三次精制', path: '/production/batches/workshop/201-3/qc-inspection', active: true },
  { key: 'refine4', label: '四次精制', path: '/production/batches/workshop/201-3/butyl-acetate' },
]

const COLUMNS: RefineColDef[] = [
  { key: 'fl_batch_no', title: '发酵液批号', group: 'fl', fmt: 'text' },
  { key: 'production_date', title: '生产日期', group: 'date', fmt: 'text' },
  { key: 'refinement_batch_no', title: '生产批号', group: 'refine', fmt: 'text' },
  { key: 'feed_batch_no', title: '投入批次', group: null, fmt: 'text', multiline: true },
  { key: 'feed_weight_kg', title: '重量(kg)', group: null, fmt: 'num' },
  { key: 'feed_pure_kg', title: '折纯(kg)', group: null, fmt: 'num' },
  { key: 'activated_carbon', title: '活性炭加量', group: null, fmt: 'num' },
  { key: 'product_weight_kg', title: '三次湿粉\n重量(kg)', group: null, fmt: 'num' },
  { key: 'product_pure_kg', title: '三次湿粉\n折纯(kg)', group: null, fmt: 'num' },
  { key: 'yield_rate', title: '收率', group: null, fmt: 'num' },
  { key: 'mother_liquor_volume', title: '母液体积', group: null, fmt: 'num' },
  { key: 'mother_liquor_unit', title: '母液单位', group: null, fmt: 'num' },
  { key: 'mother_liquor_product_kg', title: '母液产品量(kg)', group: null, fmt: 'num' },
  { key: 'impurity_6', title: '杂质6\nRRT=0.51(≤0.39)', group: null, fmt: 'num3' },
  { key: 'impurity_1', title: '杂质1\nRRT=0.59(不得检出)', group: null, fmt: 'num3' },
  { key: 'impurity_2', title: '杂质2\nRRT=0.69(≤0.7)', group: null, fmt: 'num3' },
  { key: 'impurity_7', title: '杂质7\nRRT=0.72(≤0.36)', group: null, fmt: 'num3' },
  { key: 'impurity_3', title: '杂质3\nRRT=0.88(≤0.8)', group: null, fmt: 'num3' },
  { key: 'impurity_4', title: '杂质4\nRRT=1.38(≤0.35)', group: null, fmt: 'num3' },
  { key: 'impurity_5', title: '杂质5\nRRT=1.56(≤0.50)', group: null, fmt: 'num3' },
  { key: 'rrt_068', title: 'RRT=0.68', group: null, fmt: 'num3' },
  { key: 'rrt_083', title: 'RRT=0.83', group: null, fmt: 'num3' },
  { key: 'unknown_max_single', title: '未知最大单杂', group: null, fmt: 'num3' },
  { key: 'total_impurities', title: '总杂', group: null, fmt: 'num3' },
  { key: 'purity', title: '纯度', group: null, fmt: 'num3' },
]

export default function DrThirdRefinementPage() {
  const router = useRouter()
  const { message } = App.useApp()
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [year, setYear] = useState<number>(0)
  const [month, setMonth] = useState<number>(0)
  const [years, setYears] = useState<number[]>([])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.set('table', 'dr_third_refinement')
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

  useEffect(() => {
    fetch(`${API}/api/v1/production/dr/records/years?table=dr_third_refinement`)
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
      <Card size="small" className="mb-4">
        <Space wrap>
          {STAGES.map(s => (
            <Button key={s.key} type={s.active ? 'primary' : 'default'} size="small" onClick={() => router.push(s.path)}>
              {s.label}
            </Button>
          ))}
        </Space>
      </Card>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => router.push('/production/batches/workshop/201-3')}>
            返回车间
          </Button>
          三次精制台账
        </Title>
        <Space size={8}>
          <Select size="small" style={{ width: 80 }} value={year} onChange={v => setYear(v)} options={yearOptions} />
          <Select size="small" style={{ width: 80 }} value={month} onChange={v => setMonth(v)} options={monthOptions} />
          <Text type="secondary">共 {data.length} 条</Text>
          <DRTraceButton initialModule="third_refinement" />
        </Space>
      </div>

      <Card>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '80px 0' }}>
            <Spin size="large" />
          </div>
        ) : (
          <DRRefinementTable data={data} columns={COLUMNS} />
        )}
      </Card>
    </div>
  )
}
