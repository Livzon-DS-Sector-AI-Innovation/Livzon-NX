'use client'
import { useEffect, useState } from 'react'
import { Table, Select, Card, Typography, Button, Space } from 'antd'
import {ArrowLeftOutlined,} from '@ant-design/icons'
import FASheetsSyncButton from '@/components/production/FASheetsSyncButton'
import FATraceButton from '@/components/production/FATraceButton'
import { useRouter } from 'next/navigation'

const { Title, Text } = Typography
const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

const FA_STAGES = [
  { key: 'fermentation', label: '发酵液放罐', path: '/production/batches/workshop/203/fermentation' },
  { key: 'acidification', label: '酸化过滤', path: '/production/batches/workshop/203/acidification' },
  { key: 'decolor1', label: '一次脱色过滤', path: '/production/batches/workshop/203/decolor1' },
  { key: 'mvr', label: 'MVR 浓缩', path: '/production/batches/workshop/203/mvr' },
  { key: 'mother_liquor', label: '母液溶粉', path: '/production/batches/workshop/203/mother-liquor', active: true },
  { key: 'plate_recovery', label: '板框回收', path: '/production/batches/workshop/203/plate-recovery' },
  { key: 'decolor_centrifuge', label: '脱色离心', path: '/production/batches/workshop/203/decolor-centrifuge' },
  { key: 'intermediate', label: '母液中间体', path: '/production/batches/workshop/203/intermediate' },
]
const COLS = ['日期','批号','母液打料量(m3)','溶解体积(m3)','溶解含量(g/L)','电导(ms/cm)','ph','备注']

export default function MotherLiquorPage() {
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
      const r = await fetch(`${API}/api/v1/production/fa/mother-liquor/list?page=${p}&page_size=${ps}${month > 0 ? `&month=${month}` : ''}`)
      const json = await r.json()
      if (json.code === 200) { setData(json.data.items || []); setTotal(json.data.total || 0) }
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

   
   
   
  useEffect(() => { load() }, [month]) // eslint-disable-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
useEffect(() => {    fetch(`${API}/api/v1/production/fa/monthly-averages?table=mother_liquor_records`)      .then(r => r.json()).then(j => { if(j.code===200){setAvgData(j.data.data||[]);setAvgCols(j.data.columns||[])} }).catch(()=>{})  }, [])

  return (
    <div className="p-6">
      <Card size="small" className="mb-4">
        <Space wrap>{FA_STAGES.map(s => <Button key={s.key} type={s.active ? 'primary' : 'default'} size="small" onClick={() => router.push(s.path)}>{s.label}</Button>)}</Space>
      </Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => router.push('/production/batches/workshop/203?tab=workshop')}>返回车间</Button>
          母液溶粉台账
        </Title>
        <Space><Text type="secondary">共 {total} 条</Text>
          <Select size="small" style={{ width: 76 }} value={month} onChange={v => {setMonth(v); setPage(1)}} options={[{ value: 0, label: '全部' }, ...[1,2,3,4,5,6,7,8,9,10,11,12].map(m => ({ value: m, label: `${m}月` }))]} />
          <FASheetsSyncButton />
          <FATraceButton initialModule="mother_liquor" />
        </Space>
      </div>
      {avgData.length > 0 && (
        <Card size="small" style={{ marginBottom: 12 }} title="月度平均值">
          <Table dataSource={avgData.map((r:any,i:number)=>({...r,key:i}))} size="small" pagination={false} scroll={{x:800}}
            columns={[{title:'月份',dataIndex:'月份',width:80}, ...avgCols.map((c:string)=>({title:c,dataIndex:c,width:120,render:(v:any)=>v!=null?Number(v).toLocaleString():'-'}))]} />
        </Card>
      )}
      <Card>
        <Table dataSource={data.map((r,i)=>({...r,key:r.id||i}))} loading={loading} size="small" scroll={{x:1200}}
          pagination={{total,current:page,pageSize,showTotal:(t:number)=>`共 ${t} 条`,showSizeChanger:true,
            pageSizeOptions:['10','20','50','100'],onChange:(p,ps)=>{setPage(p);setPageSize(ps);load(p,ps)}}}
          columns={COLS.map(k=>({title:k,dataIndex:k,width:k.length>10?140:80}))} />
      </Card>
    </div>
  )
}
