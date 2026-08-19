'use client'

import { useState } from 'react'
import { Button, Modal, Checkbox, Space, Typography, App, Alert, Tag } from 'antd'
import { SyncOutlined } from '@ant-design/icons'

const { Text, Paragraph } = Typography
const BACKEND = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
const API = (p: string) => `${BACKEND}/api/v1/production${p}`

interface SyncResult {
  created_fl?: number
  created_rb?: number
  created_st?: number
  created_sodium?: number
  created_acid?: number
  created_records?: number
  created_inputs?: number
  updated_records?: number
  updated_inputs?: number
  skipped?: number
  errors?: number
  error?: string
  note?: string
}

const MODULES = [
  { key: 'crude', value: 'crude', label: '粗提' },
  { key: 'extraction', value: 'extraction', label: '提取' },
  { key: 'refinement', value: 'refinement', label: '二次精制' },
  { key: 'blending', value: 'blending', label: '混粉杂质计算' },
  { key: 'qc', value: 'qc', label: '混粉入库' },
  { key: 'ba', value: 'ba', label: '丁酯盘点' },
]

export default function MCSheetsSyncButton() {
  const { message } = App.useApp()
  const [visible, setVisible] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [selected, setSelected] = useState<string[]>(['crude', 'extraction', 'refinement', 'blending', 'qc'])
  const [results, setResults] = useState<Record<string, SyncResult> | null>(null)

  const handleSync = async () => {
    if (selected.length === 0) {
      message.warning('请至少选择一个模块')
      return
    }
    setSyncing(true)
    setResults(null)
    try {
      const res = await fetch(API('/mc/sync/trigger'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modules: selected }),
      })
      const data = await res.json()
      if (data.code === 200) {
        setResults(data.data.results)
        const totalCreated = data.data.total_created || 0
        const totalUpdated = data.data.total_updated || 0
        if (totalCreated > 0 || totalUpdated > 0) {
          const parts = []
          if (totalCreated > 0) parts.push(`新建 ${totalCreated} 条`)
          if (totalUpdated > 0) parts.push(`更新 ${totalUpdated} 条`)
          message.success(`同步完成，${parts.join('，')}`)
        } else {
          message.info('同步完成，没有新数据')
        }
      } else {
        message.error(data.message || '同步失败')
      }
    } catch {
      message.error('网络错误，同步失败')
    } finally {
      setSyncing(false)
    }
  }

  const getResultTag = (r: SyncResult) => {
    if (r.error) return <Tag color="red">失败: {r.error}</Tag>
    if (r.note) return <Tag color="orange">{r.note}</Tag>
    const created = (r.created_fl || 0) + (r.created_rb || 0) + (r.created_st || 0) +
      (r.created_sodium || 0) + (r.created_acid || 0) + (r.created_records || 0) +
      (r.created_inputs || 0)
    const updated = (r.updated_records || 0) + (r.updated_inputs || 0)
    const parts = []
    if (created > 0) parts.push(`新建 ${created}`)
    if (updated > 0) parts.push(`更新 ${updated}`)
    if (parts.length > 0) return <Tag color="green">{parts.join(', ')}</Tag>
    return <Tag>无新数据</Tag>
  }

  return (
    <>
      <Button
        size="small"
        icon={<SyncOutlined spin={syncing} />}
        onClick={() => { setVisible(true); setResults(null) }}
        title="从飞书同步数据"
      >
        从飞书同步
      </Button>

      <Modal
        title="从飞书同步 MC 台账数据"
        open={visible}
        onCancel={() => setVisible(false)}
        width={500}
        footer={[
          <Button key="cancel" onClick={() => setVisible(false)}>取消</Button>,
          <Button key="sync" type="primary" icon={<SyncOutlined />} loading={syncing} onClick={handleSync}>
            开始同步
          </Button>,
        ]}
      >
        <Paragraph type="secondary" style={{ fontSize: 13 }}>
          数据源：飞书电子表格「2026年生产台账-mc」
        </Paragraph>

        <div style={{ margin: '16px 0' }}>
          <Text strong>选择同步模块：</Text>
          <Checkbox.Group
            options={MODULES}
            value={selected}
            onChange={(vals) => setSelected(vals as string[])}
            style={{ marginTop: 8 }}
          />
        </div>

        {results && (
          <div style={{ marginTop: 16 }}>
            <Text strong>同步结果：</Text>
            <div style={{ marginTop: 8 }}>
              {MODULES.filter(m => results[m.key]).map(m => (
                <div key={m.key} style={{ marginBottom: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text>{m.label}</Text>
                  {getResultTag(results[m.key])}
                </div>
              ))}
            </div>
            {Object.keys(results).some(k => results[k]?.errors) && (
              <Alert
                type="warning"
                title="部分行解析失败，请查看后端日志了解详情"
                style={{ marginTop: 8 }}
              />
            )}
          </div>
        )}
      </Modal>
    </>
  )
}
