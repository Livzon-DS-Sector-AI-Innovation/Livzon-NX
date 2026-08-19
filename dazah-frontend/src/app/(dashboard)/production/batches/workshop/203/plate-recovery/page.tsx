'use client'
import { useEffect, useState } from 'react'
import { Table, Select, Card, Typography, Button, Space, Pagination } from 'antd'
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import dayjs from 'dayjs'
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
  { key: 'plate_recovery', label: '板框回收', path: '/production/batches/workshop/203/plate-recovery', active: true },
  { key: 'decolor_centrifuge', label: '脱色离心', path: '/production/batches/workshop/203/decolor-centrifuge' },
  { key: 'intermediate', label: '母液中间体', path: '/production/batches/workshop/203/intermediate' },
]
const COLS = ['日期','白班板框进料量/方','白班板框拆卸回收粉包数','白班分液罐投回收粉包数/包','白班分液罐体积/方',
  '复滤粉拆包数','夜班板框进料量/方','夜班板框拆卸回收粉包数','夜班分液罐投回收粉包数/包','夜班分液罐体积/方',
  '复滤粉拆包数(夜)','白班装车体积','废液槽接收体积','总进料体积（m3/天）','累计进料体积m3']

export default function PlateRecoveryPage() {
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
      const r = await fetch(`${API}/api/v1/production/fa/plate-recovery/list?page=${p}&page_size=${ps}${month > 0 ? `&month=${month}` : ''}`)
      const json = await r.json()
      if (json.code === 200) { setData(json.data.items || []); setTotal(json.data.total || 0) }
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [month])
useEffect(() => {    fetch(`${API}/api/v1/production/fa/monthly-averages?table=plate_recovery_records`)      .then(r => r.json()).then(j => { if(j.code===200){setAvgData(j.data.data||[]);setAvgCols(j.data.columns||[])} }).catch(()=>{})  }, [])
  return (
    <div className="p-6">
      <Card size="small" className="mb-4">
        <Space wrap>{FA_STAGES.map(s => <Button key={s.key} type={s.active ? 'primary' : 'default'} size="small" onClick={() => router.push(s.path)}>{s.label}</Button>)}</Space>
      </Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => router.push('/production/batches/workshop/203?tab=workshop')}>返回车间</Button>
          板框回收台账
        </Title>
        <Space><Text type="secondary">共 {total} 条</Text>
          <Select size="small" style={{ width: 76 }} value={month} onChange={v => {setMonth(v); setPage(1)}} options={[{ value: 0, label: '全部' }, ...[1,2,3,4,5,6,7,8,9,10,11,12].map(m => ({ value: m, label: `${m}月` }))]} />
          <FASheetsSyncButton />
          <FATraceButton initialModule="plate_recovery" />
        </Space>
      </div>
      {avgData.length > 0 && (
        <Card size="small" style={{ marginBottom: 12 }} title="月度平均值">
          <Table dataSource={avgData.map((r:any,i:number)=>({...r,key:i}))} size="small" pagination={false} scroll={{x:1400}}
            columns={[{title:'月份',dataIndex:'月份',width:80}, ...avgCols.map((c:string)=>({title:c,dataIndex:c,width:120,render:(v:any)=>v!=null?Number(v).toLocaleString():'-'}))]} />
        </Card>
      )}
      <Card>
        <Table dataSource={data.map((r,i)=>({...r,key:r.id||i}))} loading={loading} size="small" bordered scroll={{x:1600}}
          pagination={false}
          columns={[
            { title: '日期', dataIndex: '日期', width: 70 },
            { title: '白班', children: [
              { title: '白班板框进料量/方', dataIndex: '白班板框进料量/方', width: 110 },
              { title: '白班板框拆卸回收粉包数', dataIndex: '白班板框拆卸回收粉包数', width: 140 },
              { title: '白班分液罐投回收粉包数/包', dataIndex: '白班分液罐投回收粉包数/包', width: 140 },
              { title: '白班分液罐体积/方', dataIndex: '白班分液罐体积/方', width: 100 },
              { title: '复滤粉拆包数', dataIndex: '复滤粉拆包数', width: 80 },
            ]},
            { title: '夜班', children: [
              { title: '夜班板框进料量/方', dataIndex: '夜班板框进料量/方', width: 110 },
              { title: '夜班板框拆卸回收粉包数', dataIndex: '夜班板框拆卸回收粉包数', width: 130 },
              { title: '夜班分液罐投回收粉包数/包', dataIndex: '夜班分液罐投回收粉包数/包', width: 140 },
              { title: '夜班分液罐体积/方', dataIndex: '夜班分液罐体积/方', width: 100 },
              { title: '复滤粉拆包数(夜)', dataIndex: '复滤粉拆包数(夜)', width: 90 },
            ]},
            { title: '汇总', children: [
              { title: '白班装车体积', dataIndex: '白班装车体积', width: 80 },
              { title: '废液槽接收体积', dataIndex: '废液槽接收体积', width: 80 },
              { title: '总进料体积（m3/天）', dataIndex: '总进料体积（m3/天）', width: 120 },
              { title: '累计进料体积m3', dataIndex: '累计进料体积m3', width: 100 },
            ]},
          ]} />
        <div style={{ marginTop: 12, textAlign: 'right' }}>
          <Pagination total={total} current={page} pageSize={pageSize} showTotal={(t)=>`共 ${t} 条`}
            showSizeChanger pageSizeOptions={['10','20','50','100']}
            onChange={(p,ps)=>{if(ps!==pageSize)p=1;setPage(p);setPageSize(ps);load(p,ps)}} />
        </div>
      </Card>
    </div>
  )
}
