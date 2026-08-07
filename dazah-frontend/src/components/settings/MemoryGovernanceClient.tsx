'use client'

import { useCallback, useEffect, useState } from 'react'
import { Alert, App, Button, Select, Skeleton, Space, Tag, Typography } from 'antd'
import {
  getAgentMemoryTenantPolicy,
  saveAgentMemoryTenantPolicy,
  type AgentMemoryTenantPolicy,
} from '@/actions/settings'

const { Text } = Typography

export const modeLabels = {
  auto: '自动记忆',
  explicit_only: '仅显式记忆',
  disabled: '禁用记忆',
} as const

const modeRanks: Record<keyof typeof modeLabels, number> = {
  disabled: 0,
  explicit_only: 1,
  auto: 2,
}

export function canTightenTenantMemoryPolicy(
  current: keyof typeof modeLabels,
  next: keyof typeof modeLabels,
) {
  return modeRanks[next] <= modeRanks[current]
}

export default function MemoryGovernanceClient() {
  const { message, modal } = App.useApp()
  const [policy, setPolicy] = useState<AgentMemoryTenantPolicy | null>(null)
  const [mode, setMode] = useState<AgentMemoryTenantPolicy['tenant_mode']>('auto')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getAgentMemoryTenantPolicy()
      setPolicy(result)
      setMode(result.tenant_mode)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '记忆治理策略加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const save = async () => {
    setSaving(true)
    try {
      const result = await saveAgentMemoryTenantPolicy({ mode })
      setPolicy(result)
      setMode(result.tenant_mode)
      message.success('租户记忆策略已保存')
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : '租户记忆策略保存失败')
    } finally {
      setSaving(false)
    }
  }

  const confirmSave = () => {
    modal.confirm({
      title: '确认收紧租户记忆策略？',
      content: `策略将从“${policy ? modeLabels[policy.tenant_mode] : ''}”调整为“${modeLabels[mode]}”。管理员之后不能通过此页面放宽策略。`,
      okText: '确认保存',
      cancelText: '取消',
      onOk: save,
    })
  }

  return (
    <section aria-labelledby="memory-policy-heading">
      <Space wrap align="center" size={[16, 8]}>
        <Text strong id="memory-policy-heading">记忆策略</Text>
        {loading ? <Skeleton.Input active size="small" /> : null}
        {policy ? (
          <>
            <Text type="secondary">全局</Text>
            <Tag>{modeLabels[policy.global_mode]}</Tag>
            <Text type="secondary">租户</Text>
            <Tag color="blue">{modeLabels[policy.tenant_mode]}</Tag>
            <Text type="secondary">实际上限</Text>
            <Tag color={policy.effective_mode === 'disabled' ? 'red' : 'green'}>
              {modeLabels[policy.effective_mode]}
            </Tag>
            <Select
              aria-label="租户记忆上限"
              value={mode}
              onChange={setMode}
              className="w-[160px]"
              options={Object.entries(modeLabels).map(([value, label]) => ({
                value,
                label,
                disabled: !canTightenTenantMemoryPolicy(
                  policy.tenant_mode,
                  value as keyof typeof modeLabels,
                ),
              }))}
            />
            <Button
              loading={saving}
              disabled={mode === policy.tenant_mode}
              onClick={confirmSave}
            >
              保存
            </Button>
          </>
        ) : null}
      </Space>
      {error ? (
        <Alert
          type="error"
          showIcon
          message="记忆治理策略不可用"
          description={error}
          action={<Button onClick={() => void load()}>重试</Button>}
          className="mt-3"
        />
      ) : null}
      <Text type="secondary" className="mt-2 block text-sm">
        管理员只能收紧租户上限；个人模式由用户在 Web 或飞书私聊中调整。高敏信息不保存，在线记忆清空后立即停用，灾备副本最长30天内清除。
      </Text>
    </section>
  )
}
