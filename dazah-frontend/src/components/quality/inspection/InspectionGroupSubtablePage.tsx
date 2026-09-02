'use client'

import { useEffect, useMemo, useState } from 'react'
import { Alert, App, Select, Space, Spin, Tag } from 'antd'
import { useQuery } from '@tanstack/react-query'

import { InspectionFeishuTable } from './InspectionFeishuTable'

interface InspectionSubtableItem {
  entity_code: string
  label: string
}

interface InspectionGroupSubtablePageProps {
  title: string
  module: 'solid' | 'liquid'
  group: string
}

interface FetchResult {
  data: InspectionSubtableItem[]
  configured: boolean
}

export function InspectionGroupSubtablePage({
  title,
  module,
  group,
}: InspectionGroupSubtablePageProps) {
  const { message } = App.useApp()
  const [selectedEntityCode, setSelectedEntityCode] = useState<string>()

  const subtablesApi = `/api/v1/quality/inspection-${module}/${group}/subtables`
  const recordsApi = `/api/v1/quality/inspection-${module}/${group}/records`
  const pullApi = `/api/v1/quality/inspection-${module}/${group}/pull`

  const { data, isLoading: loading, error } = useQuery<FetchResult>({
    queryKey: ['quality-inspection', 'subtables', 'inspection-group', module, group],
    queryFn: async () => {
      const res = await fetch(subtablesApi)
      const json = await res.json()
      return {
        data: Array.isArray(json.data) ? json.data as InspectionSubtableItem[] : [],
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
        style={{ width: 280 }}
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
              : '请在左侧导航栏「质量管理 -> 飞书设置」中确认对应子表实体已自动生成并已启用。'
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
      editable
    />
  )
}
