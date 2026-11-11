import Link from 'next/link'
import { Button } from 'antd'

import { fetchEmergencyPlanContent } from '@/actions/safety'
import EmergencyPlanWorkbench from '@/components/safety/EmergencyPlanWorkbench'

export const dynamic = 'force-dynamic'

export const metadata = {
  title: '应急预案 AI 工作台 | 安全管理',
}

export default async function EmergencyPlanWorkbenchPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const response = await fetchEmergencyPlanContent(id)
  const planName =
    response.code === 200 && response.data
      ? response.data.plan_name
      : '应急预案'

  return (
    <div style={{ padding: 24, height: 'calc(100vh - 120px)' }}>
      {response.code !== 200 && (
        <div style={{ marginBottom: 16, color: 'rgba(0,0,0,0.65)' }}>
          预案加载失败：{response.message || '不存在或无权限'}
          <Link href="/safety/emergency-mgmt" style={{ marginLeft: 12 }}>
            <Button size="small">返回应急管理</Button>
          </Link>
        </div>
      )}
      <EmergencyPlanWorkbench
        planId={id}
        planName={planName}
        onBackHref="/safety/emergency-mgmt"
      />
    </div>
  )
}
