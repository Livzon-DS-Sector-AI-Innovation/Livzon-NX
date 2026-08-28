'use client'

import { useEffect, useMemo, useState } from 'react'
import { Alert, App, Select, Space, Spin, Tag } from 'antd'
import { useQuery } from '@tanstack/react-query'

import { InspectionFeishuTable } from './InspectionFeishuTable'

interface MaterialSubtableItem {
  entity_code: string
  label: string
}

interface MaterialSubtablePageProps {
  title: string
  group: 'solid' | 'liquid'
}

interface FetchResult {
  data: MaterialSubtableItem[]
  configured: boolean
}

export function MaterialSubtablePage({ title, group }: MaterialSubtablePageProps) {
  const { message } = App.useApp()
  const [selectedEntityCode, setSelectedEntityCode] = useState<string>()

  const subtablesApi = `/api/v1/quality/inspection-${group}/subtables`
  const recordsApi = `/api/v1/quality/inspection-${group}/records`
  const pullApi = `/api/v1/quality/inspection-${group}/pull`

  const { data, isLoading: loading, error } = useQuery<FetchResult>({
    queryKey: ['quality-inspection', 'subtables', 'material', group],
    queryFn: async () => {
      const res = await fetch(subtablesApi)
      const json = await res.json()
      return {
        data: Array.isArray(json.data) ? json.data as MaterialSubtableItem[] : [],
        configured: json.meta?.configured !== false,
      }
    },
  })

  const subtables = useMemo(() => data?.data ?? [], [data?.data])
  const configured = error ? false : (data?.configured ?? true)

  useEffect(() => {
    if (error) {
      message.error(`加载${title}子表失败`)
      setSelectedEntityCode(undefined)
      return
    }
    if (subtables.length === 0) return
    if (!selectedEntityCode || !subtables.some((item) => item.entity_code === selectedEntityCode)) {
      setSelectedEntityCode(subtables[0]?.entity_code)
    }
  }, [subtables, selectedEntityCode, error, message, title])

  const selectedSubtable = useMemo(
    () => subtables.find((item) => item.entity_code === selectedEntityCode),
    [selectedEntityCode, subtables]
  )

  const toolbarContent = (
    <Space wrap>
      <span style={{ fontSize: 13, color: 'rgba(0, 0, 0, 0.65)' }}>子表</span>
      <Select
        value={selectedEntityCode}
        placeholder="请选择子表"
        loading={loading}
        style={{ width: 260 }}
        options={subtables.map((item) => ({
          label: item.label,
          value: item.entity_code,
        }))}
        onChange={setSelectedEntityCode}
      />
      {selectedSubtable ? <Tag color="blue">{selectedSubtable.label}</Tag> : null}
    </Space>
  )

  if (loading && subtables.length === 0) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!selectedEntityCode) {
    return (
      <div style={{ padding: 24 }}>
        <Alert
          title={configured ? '暂无可用子表' : '飞书数据源未配置'}
          description={
            configured
              ? '当前分组暂未返回可展示的子表。'
              : '请在左侧导航栏「质量管理 -> 飞书设置」中配置飞书应用凭证和实体映射。'
          }
          type={configured ? 'info' : 'warning'}
          showIcon
        />
      </div>
    )
  }

  return (
    <InspectionFeishuTable
      title={title}
      listApi={recordsApi}
      pullApi={pullApi}
      entityCode={selectedEntityCode}
      toolbarContent={toolbarContent}
    />
  )
}
