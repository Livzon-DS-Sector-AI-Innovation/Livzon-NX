'use client'
import { useEffect, useMemo, useState } from 'react'
import { Table, Card, Typography, Button, Space, Pagination, Select } from 'antd'
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import dayjs from 'dayjs'

import FASheetsSyncButton from '@/components/production/FASheetsSyncButton'
import FATraceButton from '@/components/production/FATraceButton'

const { Title, Text } = Typography
const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

const FA_STAGES = [
  { key: 'fermentation', label: '发酵液放罐', path: '/production/batches/workshop/203/fermentation', active: true },
  { key: 'acidification', label: '酸化过滤', path: '/production/batches/workshop/203/acidification' },
  { key: 'decolor1', label: '一次脱色过滤', path: '/production/batches/workshop/203/decolor1' },
  { key: 'mvr', label: 'MVR 浓缩', path: '/production/batches/workshop/203/mvr' },
  { key: 'mother_liquor', label: '母液溶粉', path: '/production/batches/workshop/203/mother-liquor' },
  { key: 'plate_recovery', label: '板框回收', path: '/production/batches/workshop/203/plate-recovery' },
  { key: 'decolor_centrifuge', label: '脱色离心', path: '/production/batches/workshop/203/decolor-centrifuge' },
  { key: 'intermediate', label: '母液中间体', path: '/production/batches/workshop/203/intermediate' },
]

const PARENT_COLS = ['放罐日期', '发酵罐号', '汇总总量_kg', '主批自身总量_kg', '电导_uscm', '调酸量_L', '酸化液滤速_ml10min', '发酵液湿固', '产量', '收率']

export default function FermentationPage() {
  const router = useRouter()
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [month, setMonth] = useState<number>(0)

  const load = async (p = 1, ps = 20) => {
    setLoading(true)
    try {
      const params = month > 0 ? `&month=${month}` : ''
      const r = await fetch(`${API}/api/v1/production/fa/fermentation/flat-list?page=${p}&page_size=${ps}${params}`)
      const json = await r.json()
      if (json.code === 200) {
        setData(json.data.items || [])
        setTotal(json.data.total || 0)
      }
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  const [avgData, setAvgData] = useState<any[]>([])
  const [avgCols, setAvgCols] = useState<string[]>([])

  useEffect(() => { load(page, pageSize) }, [month])
  useEffect(() => {
    fetch(`${API}/api/v1/production/fa/monthly-averages?table=fermentation_batches`)
      .then(r => r.json()).then(j => { if(j.code===200){setAvgData(j.data.data||[]);setAvgCols(j.data.columns||[])} }).catch(()=>{})
  }, [])

  // 预计算：给每条记录挂上 rowSpan
  const computedData = useMemo(() => {
    const result = data.map((row) => ({ ...row }))

    // 先统计每个罐号的子批数
    const groupCount: Record<string, number> = {}
    for (const row of result) {
      groupCount[row.发酵罐号] = (groupCount[row.发酵罐号] || 0) + 1
    }

    // 给每条记录挂 rowSpan
    let lastTank = ''
    for (const row of result) {
      if (row.发酵罐号 !== lastTank) {
        // 本组第一行
        row._rowSpan = groupCount[row.发酵罐号] || 1
        lastTank = row.发酵罐号
      } else {
        // 本组后续行 → 被合并
        row._rowSpan = 0
      }
    }

    return result
  }, [data])

  const makeOnCell = () => (record: any) => ({
    rowSpan: record._rowSpan ?? 1,
  })

  const renderNum = (v: any) => v != null ? (typeof v === 'number' ? v.toLocaleString() : v) : '-'

  return (
    <div className="p-6">
      <Card size="small" className="mb-4">
        <Space wrap>{FA_STAGES.map(s => <Button key={s.key} type={s.active ? 'primary' : 'default'} size="small" onClick={() => router.push(s.path)}>{s.label}</Button>)}</Space>
      </Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => router.push('/production/batches/workshop/203?tab=workshop')}>
            返回车间
          </Button>
          发酵液放罐台账
        </Title>
        <Space>
          <Text type="secondary">共 {total} 批</Text>
          <Select size="small" style={{ width: 76 }} value={month} onChange={v => {setMonth(v); setPage(1)}}
            options={[{ value: 0, label: '全部' }, ...[1,2,3,4,5,6,7,8,9,10,11,12].map(m => ({ value: m, label: `${m}月` }))]} />
          <FASheetsSyncButton />
          <FATraceButton initialModule="fermentation" />
        </Space>
      </div>
      {avgData.length > 0 && (
        <Card size="small" style={{ marginBottom: 12 }} title="月度平均值">
          <Table dataSource={avgData.map((r:any,i:number)=>({...r,key:i}))} size="small" pagination={false} scroll={{x:800}}
            columns={[{title:'月份',dataIndex:'月份',width:80}, ...avgCols.map(c=>({title:c,dataIndex:c,width:120,render:(v:any)=>v!=null?Number(v).toLocaleString():'-'}))]} />
        </Card>
      )}
      <Card>
        <Table
          dataSource={computedData.map((r, i) => ({ ...r, key: `${r.发酵罐号}_${r.子批后缀 || i}` }))}
          loading={loading}
          size="small"
          scroll={{ x: 1600 }}
          pagination={false}
          columns={[
            { title: '放罐日期', dataIndex: '放罐日期', width: 110, onCell: makeOnCell() },
            { title: '发酵罐号', dataIndex: '发酵罐号', width: 110, onCell: makeOnCell() },
            { title: '发酵批号', dataIndex: '发酵批号', width: 110 },
            { title: '体积(kl)', dataIndex: '放罐体积_kl', width: 70,
              render: (v: any) => v != null ? v.toFixed(2) : '-' },
            { title: '含量(g/L)', dataIndex: '放罐含量_gL', width: 100,
              render: (v: any) => v != null ? v.toFixed(2) : '-' },
            { title: '批总量(kg)', dataIndex: '批总量_kg', width: 130,
              render: (v: any) => renderNum(v) },
            { title: '汇总总量(kg)', dataIndex: '汇总总量_kg', width: 140,
              render: (v: any) => renderNum(v), onCell: makeOnCell() },
            { title: '电导(us/cm)', dataIndex: '电导_uscm', width: 120,
              render: (v: any) => renderNum(v), onCell: makeOnCell() },
            { title: '调酸量(L)', dataIndex: '调酸量_L', width: 100,
              render: (v: any) => renderNum(v), onCell: makeOnCell() },
            { title: '滤速', dataIndex: '酸化液滤速_ml10min', width: 80,
              render: (v: any) => renderNum(v), onCell: makeOnCell() },
            { title: '湿固', dataIndex: '发酵液湿固', width: 80, onCell: makeOnCell() },
            { title: '产量', dataIndex: '产量', width: 90,
              render: (v: any) => renderNum(v), onCell: makeOnCell() },
            { title: '收率', dataIndex: '收率', width: 80, onCell: makeOnCell() },
          ]}
        />
          <div style={{ marginTop: 12, textAlign: 'right' }}>
            <Pagination
              total={total}
              current={page}
              pageSize={pageSize}
              showTotal={(t) => `共 ${t} 批`}
              showSizeChanger
              pageSizeOptions={['10', '20', '50', '100']}
              onChange={(p, ps) => { if (ps !== pageSize) p = 1; setPage(p); setPageSize(ps); load(p, ps) }}
            />
          </div>
      </Card>
    </div>
  )
}
