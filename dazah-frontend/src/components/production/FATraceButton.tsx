'use client'

import { useState } from 'react'
import { Button, Select, Input, Space, App } from 'antd'
import { SearchOutlined, NodeIndexOutlined } from '@ant-design/icons'
import FATraceModal from './FATraceModal'
import FA_BATCH_TYPES from './faBatchTypes'


interface Props {
  initialModule?: string
  initialBatch?: string
}

export default function FATraceButton({ initialModule, initialBatch }: Props) {
  const [visible, setVisible] = useState(false)
  const [stage, setStage] = useState(initialModule || 'fermentation')
  const [batchNo, setBatchNo] = useState(initialBatch || '')
  const { message } = App.useApp()

  const handleSearch = () => {
    if (!batchNo.trim()) {
      message.warning('请输入批号')
      return
    }
    setVisible(true)
  }

  return (
    <>
      <Space size={4}>
        <Select
          size="small"
          value={stage}
          onChange={setStage}
          style={{ width: 140 }}
          options={FA_BATCH_TYPES}
        />
        <Input
          size="small"
          placeholder="输入批号追溯"
          value={batchNo}
          onChange={e => setBatchNo(e.target.value)}
          onPressEnter={handleSearch}
          style={{ width: 160 }}
          prefix={<SearchOutlined style={{ fontSize: 12, color: '#999' }} />}
        />
        <Button
          size="small"
          icon={<NodeIndexOutlined />}
          onClick={handleSearch}
          title="批次追溯"
        />
      </Space>

      {visible && (
        <FATraceModal
          stage={stage}
          batchNo={batchNo.trim()}
          onClose={() => setVisible(false)}
        />
      )}
    </>
  )
}
