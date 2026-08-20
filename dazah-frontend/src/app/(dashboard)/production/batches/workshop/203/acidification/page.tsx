'use client'
import { useEffect, useMemo, useState } from 'react'
import { Table, Select, Card, Typography, Button, Space, Pagination } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import FASheetsSyncButton from '@/components/production/FASheetsSyncButton'
import FATraceButton from '@/components/production/FATraceButton'

const { Title, Text } = Typography
const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

const FA_STAGES = [
  { key: 'fermentation', label: '发酵液放罐', path: '/production/batches/workshop/203/fermentation' },
  { key: 'acidification', label: '酸化过滤', path: '/production/batches/workshop/203/acidification', active: true },
  { key: 'decolor1', label: '一次脱色过滤', path: '/production/batches/workshop/203/decolor1' },
  { key: 'mvr', label: 'MVR 浓缩', path: '/production/batches/workshop/203/mvr' },
  { key: 'mother_liquor', label: '母液溶粉', path: '/production/batches/workshop/203/mother-liquor' },
  { key: 'plate_recovery', label: '板框回收', path: '/production/batches/workshop/203/plate-recovery' },
  { key: 'decolor_centrifuge', label: '脱色离心', path: '/production/batches/workshop/203/decolor-centrifuge' },
  { key: 'intermediate', label: '母液中间体', path: '/production/batches/workshop/203/intermediate' },
]

export default function AcidificationPage() {
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
      const r = await fetch(`${API}/api/v1/production/fa/acidification/flat-list?page=${p}&page_size=${ps}${month > 0 ? `&month=${month}` : ''}`)
      const json = await r.json()
      if (json.code === 200) {
        setData(json.data.items || [])
        setTotal(json.data.total || 0)
      }
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

   
   
   
  useEffect(() => { load() }, [month]) // eslint-disable-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
useEffect(() => {    fetch(`${API}/api/v1/production/fa/monthly-averages?table=acidification_records`)      .then(r => r.json()).then(j => { if(j.code===200){setAvgData(j.data.data||[]);setAvgCols(j.data.columns||[])} }).catch(()=>{})  }, [])

  const computedData = useMemo(() => {
    const result = data.map((row) => ({ ...row }))
    const groupCount: Record<string, number> = {}
    for (const row of result) {
      const k = row.批号 || '__none__'
      groupCount[k] = (groupCount[k] || 0) + 1
    }
    let lastBatch = ''
    for (const row of result) {
      if (row.批号 !== lastBatch) {
        row._rowSpan = groupCount[row.批号 || '__none__'] || 1
        lastBatch = row.批号
      } else {
        row._rowSpan = 0
      }
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
          酸化过滤台账
        </Title>
        <Space>
          <Text type="secondary">共 {total} 行</Text>
          <Select size="small" style={{ width: 76 }} value={month} onChange={v => {setMonth(v); setPage(1)}} options={[{ value: 0, label: '全部' }, ...[1,2,3,4,5,6,7,8,9,10,11,12].map(m => ({ value: m, label: `${m}月` }))]} />
          <FASheetsSyncButton />
          <FATraceButton initialModule="acidification" />
        </Space>
      </div>
      {avgData.length > 0 && (
        <Card size="small" style={{ marginBottom: 12 }} title="月度平均值">
          <Table dataSource={avgData.map((r:any,i:number)=>({...r,key:i}))} size="small" pagination={false} scroll={{x:2000}}
            columns={[{title:'月份',dataIndex:'月份',width:80}, ...avgCols.map((c:string)=>({title:c,dataIndex:c,width:120,render:(v:any)=>v!=null?Number(v).toLocaleString():'-'}))]} />
        </Card>
      )}
      <Card>
        <Table
          dataSource={computedData.map((r, i) => ({ ...r, key: r.id || i }))}
          loading={loading} size="small" bordered scroll={{ x: 2300 }}
          pagination={false}
          columns={[
            { title: '日期', dataIndex: '日期', width: 66, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
            { title: '批号', dataIndex: '批号', width: 84, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
            { title: '发酵液', children: [
              { title: '发酵液体积（kl)', dataIndex: '发酵液体积（kl)', width: 84 },
              { title: '发酵液含量（g/L）', dataIndex: '发酵液含量（g/L）', width: 84 },
              { title: '发酵液罐产（kg）', dataIndex: '发酵液罐产（kg）', width: 84, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
            ]},
            { title: '酸化液', children: [
              { title: '用酸量（95-98%浓硫酸）', dataIndex: '用酸量（95-98%浓硫酸）', width: 90, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
              { title: 'PH（酸化后）', dataIndex: 'PH（酸化后）', width: 60 },
              { title: '酸化液体积（kl)', dataIndex: '酸化液体积（kl)', width: 84, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
              { title: '理论酸化液含量（g/L）', dataIndex: '理论酸化液含量（g/L）', width: 90, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }), render: (v: any) => v != null ? Number(v).toFixed(2) : '' },
            ]},
            { title: '酸化滤液', children: [
              { title: 'PH', dataIndex: 'PH', width: 48 },
              { title: '膜滤液体积（KL）', dataIndex: '膜滤液体积（KL）', width: 84 },
              { title: '膜滤液含量（g/L）', dataIndex: '膜滤液含量（g/L）', width: 84 },
              { title: '膜滤液产品量（kg）', dataIndex: '膜滤液产品量（kg）', width: 84 },
              { title: '膜滤液产品总量（kg）', dataIndex: '膜滤液产品总量（kg）', width: 90, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
              { title: '本批低单位含量（g/L）', dataIndex: '本批低单位含量（g/L）', width: 90 },
              { title: '本批低单位体积（KL）', dataIndex: '本批低单位体积（KL）', width: 90 },
              { title: '本批低单位苯产品（kg）', dataIndex: '本批低单位苯产品（kg）', width: 96 },
              { title: '本批低单位量（kg）', dataIndex: '本批低单位量（kg）', width: 84, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
              { title: '上批套用低单位量（kg）', dataIndex: '上批套用低单位量（kg）', width: 90, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
            ]},
            { title: '渣液', children: [
              { title: '批收率', dataIndex: '批收率', width: 54, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
              { title: '顶洗前体积（kl）', dataIndex: '顶洗前体积（kl）', width: 78, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
              { title: '尾液含量（g/L）', dataIndex: '尾液含量（g/L）', width: 72, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
              { title: '渣含量（g/L）', dataIndex: '渣含量（g/L）', width: 72, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
              { title: '体积（罐渣+膜渣（kl）', dataIndex: '体积（罐渣+膜渣（kl）', width: 90, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
              { title: '渣产品量（kg）', dataIndex: '渣产品量（kg）', width: 72, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
              { title: '渣损失率（渣苯丙量/罐产）', dataIndex: '渣损失率（渣苯丙量/罐产）', width: 90, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
            ]},
            { title: '标准数据', children: [
              { title: '渣体积/发酵液体积', dataIndex: '渣体积/发酵液体积', width: 90, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
              { title: '酸化液/发酵液体积', dataIndex: '酸化液/发酵液体积', width: 90, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
              { title: '滤液体积/发酵液体积', dataIndex: '滤液体积/发酵液体积', width: 90, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
              { title: '平衡率', dataIndex: '平衡率', width: 60, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
              { title: '消泡剂使用量（L）', dataIndex: '消泡剂使用量（L）', width: 90, onCell: (r: any) => ({ rowSpan: r._rowSpan ?? 1 }) },
            ]},
          ]}
        />
        <div style={{ marginTop: 12, textAlign: 'right' }}>
          <Pagination total={total} current={page} pageSize={pageSize} showTotal={(t)=>`共 ${t} 行`}
            showSizeChanger pageSizeOptions={['10','20','50','100']}
            onChange={(p,ps)=>{if(ps!==pageSize)p=1;setPage(p);setPageSize(ps);load(p,ps)}} />
        </div>
      </Card>
    </div>
  )
}
