'use client'

import { useState } from 'react'
import { Button, Select, Input, Space, Typography, App } from 'antd'
import { SearchOutlined, NodeIndexOutlined } from '@ant-design/icons'
import DRTraceModal from './DRTraceModal'
import { getDRFieldOptions } from './drBatchTypes'


interface Props {
  initialModule?: string
  initialBatch?: string
}

export default function DRTraceButton({ initialModule, initialBatch }: Props) {
  const [visible, setVisible] = useState(false)
  const [stage, setStage] = useState(initialModule || 'second_refinement')
  const [batchNo, setBatchNo] = useState(initialBatch || '')
  const { message } = App.useApp()
  // 下拉按当前工段页显示该表实际批号字段（未配置时回退全部工段）
  const fieldOptions = getDRFieldOptions(initialModule || '')

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
          style={{ width: 184 }}
          options={fieldOptions}
        />
        <Input
          size="small"
          placeholder="输入批号查询"
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
          title="追溯"
        />
      </Space>

      {visible && (
        <DRTraceModal
          stage={stage}
          batchNo={batchNo.trim()}
          onClose={() => setVisible(false)}
        />
      )}
    </>
  )
}
