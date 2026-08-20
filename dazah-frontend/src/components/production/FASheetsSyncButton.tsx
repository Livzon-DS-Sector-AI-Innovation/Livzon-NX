'use client'

import { useState } from 'react'
import {Button, Modal, Checkbox, Typography, App, Tag} from 'antd'
import { SyncOutlined } from '@ant-design/icons'

const { Text, Paragraph } = Typography
const BACKEND = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
const API = (p: string) => `${BACKEND}/api/v1/production${p}`

const MODULES = [
  { key: 'fermentation', value: 'fermentation', label: '发酵液放罐' },
  { key: 'acidification', value: 'acidification', label: '酸化过滤' },
  { key: 'decolor1', value: 'decolor1', label: '一次脱色过滤' },
  { key: 'mvr', value: 'mvr', label: 'MVR 浓缩' },
  { key: 'mother_liquor', value: 'mother_liquor', label: '母液溶粉' },
  { key: 'plate_recovery', value: 'plate_recovery', label: '板框回收' },
  { key: 'decolor_centrifuge', value: 'decolor_centrifuge', label: '脱色离心' },
  { key: 'intermediate', value: 'intermediate', label: '母液中间体' },
]

export default function FASheetsSyncButton() {
  const { message } = App.useApp()
  const [visible, setVisible] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [selected, setSelected] = useState<string[]>(MODULES.map(m => m.key))
  const [results, setResults] = useState<Record<string, any> | null>(null)

  const handleSync = async () => {
    if (selected.length === 0) { message.warning('请至少选择一个模块'); return }
    setSyncing(true)
    setResults(null)
    try {
      const res = await fetch(API('/fa/sync/trigger'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modules: selected }),
      })
      const data = await res.json()
      if (data.code === 200) {
        setResults(data.data.results)
        const errors = data.data.errors || 0
        if (errors > 0) {
          message.warning(`同步完成，${errors} 个模块失败`)
        } else {
          message.success('同步完成')
        }
      } else {
        message.error(data.message || '同步失败')
      }
    } catch { message.error('网络错误，同步失败') }
    finally { setSyncing(false) }
  }

  const getTag = (r: any) => {
    if (!r) return <Tag>无数据</Tag>
    if (r.error) return <Tag color="red">失败: {r.error}</Tag>
    const batches = r.batches || 0
    const subs = r.sub_batches || 0
    const rows = r.rows || 0
    if (batches) return <Tag color="green">新建/更新 {batches} 批 + {subs} 子批</Tag>
    if (rows) return <Tag color="green">新建/更新 {rows} 行</Tag>
    return <Tag color="green">完成</Tag>
  }

  return (
    <>
      <Button icon={<SyncOutlined />} onClick={() => { setVisible(true); setResults(null) }}>
        从飞书同步
      </Button>

      <Modal
        title="从飞书同步 FA 台账数据"
        open={visible}
        onCancel={() => setVisible(false)}
        width={500}
        footer={[
          <Button key="cancel" onClick={() => setVisible(false)}>取消</Button>,
          <Button key="sync" type="primary" icon={<SyncOutlined />} loading={syncing} onClick={handleSync}>开始同步</Button>,
        ]}
      >
        <Paragraph type="secondary" style={{ fontSize: 13 }}>
          数据源：飞书电子表格「苯丙酸化过滤+脱色离心台账」
        </Paragraph>

        <div style={{ margin: '16px 0' }}>
          <Text strong>选择同步模块：</Text>
          <Checkbox.Group options={MODULES} value={selected}
            onChange={(vals) => setSelected(vals as string[])} style={{ marginTop: 8 }} />
        </div>

        {results && (
          <div style={{ marginTop: 16 }}>
            <Text strong>同步结果：</Text>
            <div style={{ marginTop: 8 }}>
              {MODULES.filter(m => results[m.key]).map(m => (
                <div key={m.key} style={{ marginBottom: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text>{m.label}</Text> {getTag(results[m.key])}
                </div>
              ))}
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}
