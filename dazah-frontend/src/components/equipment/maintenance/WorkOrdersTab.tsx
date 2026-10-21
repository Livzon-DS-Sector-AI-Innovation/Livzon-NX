'use client'

import { useEffect, useState } from 'react'
import { App, Button, Collapse, InputNumber, Space } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { useEquipmentStore } from '@/stores/equipment'
import { fetchClaimTimeoutConfigClient } from '@/lib/api/equipment-client'
import { updateClaimTimeoutConfig } from '@/actions/equipment'
import { WorkOrderStatsCards } from '../WorkOrderStatsCards'
import { WorkOrderTable } from '../WorkOrderTable'

interface WorkOrdersTabProps {
  onRefresh: () => void | Promise<void>
}

/** 维修工单 Tab：统计卡 + 抢单超时配置 + 工单列表 */
export function WorkOrdersTab({ onRefresh }: WorkOrdersTabProps) {
  const { workOrderStatistics, openWorkOrderDrawer } = useEquipmentStore()
  const { message: configMsg } = App.useApp()

  const [claimTimeoutConfig, setClaimTimeoutConfig] = useState({
    emergency: 15, high: 30, medium: 60, low: 120,
  })

  useEffect(() => {
    fetchClaimTimeoutConfigClient().then(setClaimTimeoutConfig).catch(() => {})
  }, [])

  const handleSaveConfig = async () => {
    try {
      await updateClaimTimeoutConfig(claimTimeoutConfig)
      configMsg.success('超时配置保存成功')
    } catch (error) {
      configMsg.error(error?.message || '保存配置失败')
    }
  }

  return (
    <div>
      <WorkOrderStatsCards statistics={workOrderStatistics} />

      <Collapse
        style={{ marginTop: 16, marginBottom: 16 }}
        items={[{
          key: 'timeout-config',
          label: '抢单超时配置',
          children: (
            <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              {[
                { key: 'emergency', label: '紧急', color: '#e03131' },
                { key: 'high', label: '高', color: '#dd5b00' },
                { key: 'medium', label: '中', color: '#5645d4' },
                { key: 'low', label: '低', color: '#787671' },
              ].map(({ key, label, color }) => (
                <div key={key}>
                  <div style={{ marginBottom: 4, fontSize: 13, color, fontWeight: 500 }}>{label}优先级</div>
                  <Space.Compact>
                    <InputNumber
                      min={1} max={1440}
                      value={claimTimeoutConfig[key as keyof typeof claimTimeoutConfig]}
                      onChange={(v) => setClaimTimeoutConfig(prev => ({ ...prev, [key]: v || 15 }))}
                    />
                    <Button disabled>分钟</Button>
                  </Space.Compact>
                </div>
              ))}
              <Button type="primary" onClick={handleSaveConfig}>保存配置</Button>
            </div>
          ),
        }]}
      />

      <div style={{ marginTop: 16 }}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold" style={{ fontSize: 18, color: '#1a1a1a', lineHeight: 1.4, margin: 0 }}>
            工单列表
          </h2>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openWorkOrderDrawer()}>
            新建工单
          </Button>
        </div>
        <WorkOrderTable onRefresh={onRefresh} />
      </div>
    </div>
  )
}
