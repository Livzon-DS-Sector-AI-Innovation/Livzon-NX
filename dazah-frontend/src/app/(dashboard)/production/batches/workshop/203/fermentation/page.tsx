'use client'
import { Button, Typography } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'

const { Title } = Typography

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

export default function Workshop203FermentationPage() {
  const router = useRouter()
  return (
    <div className="p-6">
      <Title level={4} style={{ margin: 0 }}>
        <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => router.push('/production/batches/workshop/203')}>返回车间</Button>
        发酵液放罐
      </Title>
      <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
        {FA_STAGES.map(s => (
          <Button key={s.key} type={s.active ? 'primary' : 'default'} size="small" onClick={() => router.push(s.path)}>{s.label}</Button>
        ))}
      </div>
    </div>
  )
}
