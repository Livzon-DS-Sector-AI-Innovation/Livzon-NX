'use client'
import { useEffect, useMemo, useState } from 'react'
import { Table, Select, Card, Typography, Button, Space, Pagination } from 'antd'
import {ArrowLeftOutlined,} from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import FASheetsSyncButton from '@/components/production/FASheetsSyncButton'
import FATraceButton from '@/components/production/FATraceButton'
const { Title, Text } = Typography
const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

const FA_STAGES = [
  { key: 'fermentation', label: '发酵液放罐', path: '/production/batches/workshop/203/fermentation' },
  { key: 'acidification', label: '酸化过滤', path: '/production/batches/workshop/203/acidification' },
  { key: 'decolor1', label: '一次脱色过滤', path: '/production/batches/workshop/203/decolor1' },
  { key: 'mvr', label: 'MVR 浓缩', path: '/production/batches/workshop/203/mvr' },
  { key: 'mother_liquor', label: '母液溶粉', path: '/production/batches/workshop/203/mother-liquor' },
  { key: 'plate_recovery', label: '板框回收', path: '/production/batches/workshop/203/plate-recovery' },
  { key: 'decolor_centrifuge', label: '脱色离心', path: '/production/batches/workshop/203/decolor-centrifuge', active: true },
  { key: 'intermediate', label: '母液中间体', path: '/production/batches/workshop/203/intermediate' },
]

export default function DecolorCentrifugePage() {
  const router = useRouter()
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [month, setMonth] = useState<number>(0)
  const [avgData, setAvgData] = useState<any[]>([])
  const [avgCols, setAvgCols] = useState<string[]>([])
  const load = async (p = 1, ps = 20) => {
    setLoading(true)
    try {
      const r = await fetch(`${API}/api/v1/production/fa/decolor-centrifuge/list?page=${p}&page_size=${ps}${month > 0 ? `&month=${month}` : ''}`)
      const json = await r.json()
      if (json.code === 200) { setData(json.data.items || []); setTotal(json.data.total || 0) }
    } catch (e) { console.error(e) } finally { setLoading(false) }
  }
   
   
   
  useEffect(() => { load() }, [month]) // eslint-disable-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => {
    fetch(`${API}/api/v1/production/fa/monthly-averages?table=decolor_centrifuge_records`)
      .then(r => r.json()).then(j => { if(j.code===200){setAvgData(j.data.data||[]);setAvgCols(j.data.columns||[])} }).catch(()=>{})
  }, [])

  const computedData = useMemo(() => {
    const result = data.map(r => ({...r}))
    const gc: Record<string, number> = {}
    for (const r of result) { const k = r.日期 || '__none__'; gc[k] = (gc[k] || 0) + 1 }
    let ld = ''
    for (const r of result) {
      if (r.日期 !== ld) { r._rowSpan = gc[r.日期 || '__none__'] || 1; ld = r.日期 }
      else { r._rowSpan = 0 }
    }
    return result
  }, [data])

  return (
    <div className="p-6">
      <Card size="small" className="mb-4">
        <Space wrap>{FA_STAGES.map(s => <Button key={s.key} type={s.active ? 'primary' : 'default'} size="small" onClick={() => router.push(s.path)}>{s.label}</Button>)}</Space>
      </Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => router.push('/production/batches/workshop/203?tab=workshop')}>返回车间</Button>
          脱色离心台账
        </Title>
        <Space><Text type="secondary">共 {total} 条</Text>
          <Select size="small" style={{ width: 76 }} value={month} onChange={v => {setMonth(v); setPage(1)}} options={[{ value: 0, label: '全部' }, ...[1,2,3,4,5,6,7,8,9,10,11,12].map(m => ({ value: m, label: `${m}月` }))]} />
          <FASheetsSyncButton />
          <FATraceButton initialModule="decolor_centrifuge" />
        </Space>
      </div>
      {avgData.length > 0 && (
        <Card size="small" style={{ marginBottom: 12 }} title="月度平均值">
          <Table dataSource={avgData.map((r:any,i:number)=>({...r,key:i}))} size="small" pagination={false} scroll={{x:1600}}
            columns={[{title:'月份',dataIndex:'月份',width:80}, ...avgCols.map((c:string)=>({title:c,dataIndex:c,width:120,render:(v:any)=>v!=null?Number(v).toLocaleString():'-'}))]} />
        </Card>
      )}
      <Card>
        <Table dataSource={computedData.map((r,i)=>({...r,key:r.id||i}))} loading={loading} size="small" bordered
          scroll={{x:2600}}
          pagination={false}
          columns={[
            { title: '日期', dataIndex: '日期', width: 80, onCell: (r:any)=>({rowSpan:r._rowSpan??1}) },
            { title: '批号', dataIndex: '批号', width: 110 },
            { title: '一次浓缩', children: [
              { title: '进料体积（kl）', dataIndex: '进料体积（kl）', width: 100 },
              { title: '出料体积（kl）', dataIndex: '出料体积（kl）', width: 100 },
            ]},
            { title: '一次离心', children: [
              { title: '顶洗时长（min）', dataIndex: '顶洗时长（min）', width: 100 },
              { title: '甩料车数', dataIndex: '甩料车数', width: 80 },
              { title: '水分（%）', dataIndex: '水分（%）', width: 80 },
            ]},
            { title: '二次脱色', children: [
              { title: '碳前', children: [
                { title: '体积（kl）', dataIndex: '体积（kl）', width: 90 },
                { title: '炭脱PH', dataIndex: '炭脱PH', width: 90 },
                { title: '炭前真实含量（g/L）', dataIndex: '炭前真实含量（g/L）', width: 90 },
                { title: '炭前总量', dataIndex: '炭前总量', width: 90 },
              ]},
              { title: '碳后', children: [
                { title: '活性炭用量（kg)', dataIndex: '活性炭用量（kg)', width: 90 },
                { title: '活性炭品牌', dataIndex: '活性炭品牌', width: 90 },
                { title: '炭后真实含量(g/L）', dataIndex: '炭后真实含量(g/L）', width: 90 },
                { title: '透光（%）', dataIndex: '透光（%）', width: 80 },
                { title: '亚硫酸氢钠（kg）', dataIndex: '亚硫酸氢钠（kg）', width: 100 },
              ]},
            ]},
            { title: '废碳', children: [
              { title: '顶洗时长（min)', dataIndex: '顶洗时长（min)2', width: 100 },
              { title: '甩料车数', dataIndex: '二次离心_甩料车数', width: 80 },
              { title: '顶洗次数', dataIndex: '二次离心_顶洗次数', width: 80 },
            ]},
            { title: '收率', dataIndex: '收率', width: 80 },
            { title: '二次离心', children: [
              { title: '批号', dataIndex: '二次离心_批号', width: 110 },
              { title: '甩料车数', dataIndex: '二次离心_甩料车数', width: 80 },
              { title: '顶洗次数', dataIndex: '二次离心_顶洗次数', width: 80 },
            ]},
          ]}
        />
        <div style={{ marginTop: 12, textAlign: 'right' }}>
          <Pagination total={total} current={page} pageSize={pageSize} showTotal={(t)=>`共 ${t} 条`}
            showSizeChanger pageSizeOptions={['10','20','50','100']}
            onChange={(p,ps)=>{if(ps!==pageSize)p=1;setPage(p);setPageSize(ps);load(p,ps)}} />
        </div>
      </Card>
    </div>
  )
}
