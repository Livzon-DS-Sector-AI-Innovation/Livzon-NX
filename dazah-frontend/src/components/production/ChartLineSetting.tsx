'use client'
// 图表警戒线配置入口：按钮 + 弹窗（数值编辑、保存回调、全平台共享提示）。

import { useState } from 'react'
import { App, Button, InputNumber, Modal, Typography } from 'antd'
import { SettingOutlined } from '@ant-design/icons'
import type { ChartLineConfig } from './chart-thresholds'

const { Text } = Typography

interface ChartLineSettingProps {
  configs: ChartLineConfig[]
  /** 展示值（含图表缺省线值），保存回调成功后由调用方刷新 */
  values: Record<string, number | undefined>
  onSave: (chartKey: string, threshold: number) => Promise<boolean>
  title?: string
  buttonText?: string
}

export default function ChartLineSetting({
  configs,
  values,
  onSave,
  title = '警戒线配置（全平台共享）',
  buttonText = '警戒线',
}: ChartLineSettingProps) {
  const { message } = App.useApp()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Record<string, number | undefined>>({})
  const [saving, setSaving] = useState(false)

  const openModal = () => {
    const d: Record<string, number | undefined> = {}
    for (const conf of configs) d[conf.key] = values[conf.key]
    setDraft(d)
    setOpen(true)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      for (const conf of configs) {
        const v = draft[conf.key]
        if (v == null) continue
        const ok = await onSave(conf.key, v)
        if (!ok) {
          message.error(`「${conf.label}」保存失败`)
          return
        }
      }
      message.success('警戒线已保存，全平台生效')
      setOpen(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Button size="small" icon={<SettingOutlined />} onClick={openModal}>
        {buttonText}
      </Button>
      <Modal
        title={title}
        open={open}
        onOk={handleSave}
        onCancel={() => setOpen(false)}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        width={420}
      >
        {configs.map((conf) => (
          <div key={conf.key} style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
            <Text style={{ flex: 1 }}>{conf.label}{conf.unit ? `（${conf.unit}）` : ''}</Text>
            <InputNumber
              aria-label={conf.label}
              value={draft[conf.key]}
              onChange={(v) => setDraft((prev) => ({ ...prev, [conf.key]: v ?? undefined }))}
              style={{ width: 120 }}
            />
          </div>
        ))}
        <Text type="secondary">保存后立即按新值生效，对所有用户生效。</Text>
      </Modal>
    </>
  )
}
