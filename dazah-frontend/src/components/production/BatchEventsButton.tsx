'use client'

import { useState } from 'react'
import { Button, Modal, Typography } from 'antd'
import { AlertOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'

const { Text, Paragraph } = Typography

interface BatchEventsButtonProps {
  batchId: string
  batchLabel: string
  status: string
}

export default function BatchEventsButton({ batchId, batchLabel, status }: BatchEventsButtonProps) {
  const [visible, setVisible] = useState(false)
  const [events, setEvents] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  if (status !== 'in_progress') return null

  const open = async () => {
    setVisible(true); setEvents([]); setLoading(true)
    try {
      const res = await fetch(`http://localhost:8000/api/v1/production/fermentation/${batchId}/related-events`)
      const json = await res.json()
      if (json.code === 200) setEvents(json.data)
    } catch {} finally { setLoading(false) }
  }

  return (
    <>
      <Button type="link" size="small" icon={<AlertOutlined />} style={{ color: '#faad14' }} onClick={open}>异常</Button>
      <Modal title={`${batchLabel} · 运行期间异常事件`} open={visible} onCancel={() => setVisible(false)} footer={null} width={640} loading={loading}>
        {events.length === 0 ? <Text type="secondary">暂无异常事件记录</Text> : (
          events.map((ev: any) => {
            const txt = ev.restore_time
              ? `${dayjs(ev.event_time).format('YYYY年M月D日 HH:mm')}，${ev.workshop}发生${ev.event_type}${ev.description ? '：' + ev.description : ''}${ev.impact_scope ? '。影响范围：' + ev.impact_scope : ''}${ev.action_taken ? '。处理措施：' + ev.action_taken : ''}。于${dayjs(ev.restore_time).format('M月D日 HH:mm')}恢复正常${ev.impact_duration ? '，影响时长' + ev.impact_duration : ''}。`
              : `${dayjs(ev.event_time).format('YYYY年M月D日 HH:mm')}，${ev.workshop}发生${ev.event_type}${ev.description ? '：' + ev.description : ''}。`
            return <Paragraph key={ev.id} style={{ fontSize: 14, lineHeight: 2, padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>{txt}</Paragraph>
          })
        )}
      </Modal>
    </>
  )
}
