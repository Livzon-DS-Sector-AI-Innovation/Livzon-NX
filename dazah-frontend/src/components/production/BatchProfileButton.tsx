'use client'

import { useState } from 'react'
import { Button, Modal, Descriptions, Tag, Card, Typography, Divider, Spin } from 'antd'
import { NodeIndexOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'

const { Text, Title } = Typography
const BACKEND = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
const SCT = 'seed_culture'

interface Props { batchNo: string }

export default function BatchProfileButton({ batchNo }: Props) {
  const [visible, setVisible] = useState(false)
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<any>(null)

  const open = async () => {
    setVisible(true); setData(null); setLoading(true)
    try {
      const res = await fetch(`${BACKEND}/api/v1/production/batch-profile/${encodeURIComponent(batchNo)}`)
      const json = await res.json()
      if (json.code === 200) setData(json.data)
    } catch {} finally { setLoading(false) }
  }

  const renderSeedCulture = (sc: any) => (
    <Descriptions bordered size="small" column={6} title={<Text strong style={{ fontSize: 14 }}>🧬 菌种制备（101一车间）</Text>}>
      <Descriptions.Item label="产品">{sc.product_name}</Descriptions.Item>
      <Descriptions.Item label="配制日期">{sc.prepare_date || '-'}</Descriptions.Item>
      <Descriptions.Item label="物料A">{sc.glucose_batch || '-'}</Descriptions.Item>
      <Descriptions.Item label="物料B">{sc.corn_starch_batch || '-'}</Descriptions.Item>
      <Descriptions.Item label="物料C">{sc.corn_syrup_batch || '-'}</Descriptions.Item>
      <Descriptions.Item label="物料D">{sc.ammonium_sulfate_batch || '-'}</Descriptions.Item>
      <Descriptions.Item label="物料E">{sc.soybean_meal_batch || '-'}</Descriptions.Item>
      <Descriptions.Item label="物料F">{sc.calcium_carbonate_batch || '-'}</Descriptions.Item>
      <Descriptions.Item label="配制操作人">{sc.prepare_operator || '-'}</Descriptions.Item>
      <Descriptions.Item label="种子消毒人员">{sc.sterilization_operator || '-'}</Descriptions.Item>
      <Descriptions.Item label="冻管菌号">{sc.strain_tube_no || '-'}</Descriptions.Item>
      <Descriptions.Item label="调前PH">{sc.ph_before_adjust ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="调后PH">{sc.ph_after_adjust ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="消后PH">{sc.ph_after_sterilization ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="还原糖">{sc.reducing_sugar ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="总糖">{sc.total_sugar ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="氨基氮">{sc.amino_nitrogen ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="摇床编号">{sc.shaker_no || '-'}</Descriptions.Item>
      <Descriptions.Item label="上摇床日期">{sc.shaker_start_date || '-'}</Descriptions.Item>
      <Descriptions.Item label="接种人员">{sc.inoculation_operator || '-'}</Descriptions.Item>
      <Descriptions.Item label="用具编号">{sc.tool_no || '-'}</Descriptions.Item>
      <Descriptions.Item label="并瓶PH">{sc.merge_ph ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="并瓶菌浓">{sc.merge_bacteria_density ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="罐产">{sc.tank_yield ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="备注">{sc.remarks || '-'}</Descriptions.Item>
    </Descriptions>
  )

  const renderFermentation = (ferms: any[]) => (
    <div>
      <Text strong style={{ fontSize: 14 }}>🏭 发酵记录</Text>
      {ferms.map((f: any, i: number) => (
        <Descriptions key={i} bordered size="small" column={4} className="mt-2">
          <Descriptions.Item label="发酵罐">{f.fermenter}</Descriptions.Item>
          <Descriptions.Item label="产品">{f.product_name}</Descriptions.Item>
          <Descriptions.Item label="进罐日期">{f.entry_date || '-'}</Descriptions.Item>
          <Descriptions.Item label="放罐日期">{f.discharge_date || '进行中'}</Descriptions.Item>
          <Descriptions.Item label="状态"><Tag color="processing">{f.status === 'in_progress' ? '运行中' : f.status}</Tag></Descriptions.Item>
          <Descriptions.Item label="罐产">{f.tank_yield ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="备注">{f.remarks || '-'}</Descriptions.Item>
        </Descriptions>
      ))}
    </div>
  )

  const renderEvents = (events: any[]) => (
    <div>
      <Text strong style={{ fontSize: 14 }}>⚠ 关联异常事件（{events.length}）</Text>
      {events.length === 0 ? <div className="mt-2"><Text type="secondary">无</Text></div> : (
        events.map((ev: any) => (
          <Card key={ev.id} size="small" className="mt-2">
            <Text>{dayjs(ev.event_time).format('MM-DD HH:mm')} {ev.workshop} {ev.event_type}{ev.description ? '：' + ev.description : ''}，影响{ev.impact_duration || '—'}</Text>
          </Card>
        ))
      )}
    </div>
  )

  const renderRefinery = (refinery: any) => {
    const labels: Record<string, string> = {
      broth_receive: '发酵液接收', pretreatment: '预处理', ceramic_feed: '陶瓷膜·进料',
      ceramic_ops: '陶瓷膜·运行', ceramic_clean: '陶瓷膜·清洗', ceramic_sep: '陶瓷膜·分离',
      ceramic_equip: '陶瓷膜·设备', decolor1: '一次脱色',
    }
    const entries = Object.entries(refinery || {}).filter(([_, v]: any) => v?.length > 0)
    if (!entries.length) return null
    return (
      <div>
        <Divider />
        <Text strong style={{ fontSize: 14 }}>🏭 提炼车间</Text>
        {entries.map(([key, items]: any) => (
          <div key={key} className="mt-2">
            <Text type="secondary">{labels[key] || key}（{items.length}条）</Text>
          </div>
        ))}
      </div>
    )
  }

  return (
    <>
      <Button type="link" size="small" icon={<NodeIndexOutlined />} style={{ color: '#1677ff' }} onClick={open}>全貌</Button>
      <Modal title={`批次全貌：${batchNo}`} open={visible} onCancel={() => setVisible(false)} footer={null} width={960}>
        {loading ? <Spin /> : data ? (
          <div>
            {data[SCT] && renderSeedCulture(data[SCT])}
            {data[SCT] && data.fermentation?.length > 0 && <Divider />}
            {data.fermentation?.length > 0 && renderFermentation(data.fermentation)}
            {data.events && <Divider />}
            {data.events && renderEvents(data.events)}
{data.refinery && renderRefinery(data.refinery)}
          </div>
        ) : (
          <Text type="secondary">未找到该批号关联记录</Text>
        )}
      </Modal>
    </>
  )
}
