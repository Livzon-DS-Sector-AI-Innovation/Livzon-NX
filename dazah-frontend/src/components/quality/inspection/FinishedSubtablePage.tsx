'use client'

import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Alert, App, Select, Space, Spin, Tag } from 'antd'
import { useQuery } from '@tanstack/react-query'

import { InspectionFeishuTable } from './InspectionFeishuTable'

interface FinishedSubtableItem {
  entity_code: string
  label: string
}

interface FinishedSubtablePageProps {
  title: string
  productGroup: string
  dashboardContent?: ReactNode
  renderDashboardContent?: (context: {
    selectedEntityCode?: string
    subtables: FinishedSubtableItem[]
  }) => ReactNode
}

interface FetchResult {
  data: FinishedSubtableItem[]
  configured: boolean
}

export function FinishedSubtablePage({
  title,
  productGroup,
  dashboardContent,
  renderDashboardContent,
}: FinishedSubtablePageProps) {
  const { message } = App.useApp()
  const [selectedEntityCode, setSelectedEntityCode] = useState<string>()
  const [toolbarContainer, setToolbarContainer] = useState<HTMLDivElement | null>(null)

  const subtablesApi = `/api/v1/quality/inspection-finished/${productGroup}/subtables`
  const recordsApi = `/api/v1/quality/inspection-finished/${productGroup}/records`

  const { data, isLoading: loading, error } = useQuery<FetchResult>({
    queryKey: ['quality-inspection', 'subtables', 'finished', productGroup],
    queryFn: async () => {
      const res = await fetch(subtablesApi)
      const json = await res.json()
      return {
        data: Array.isArray(json.data) ? json.data as FinishedSubtableItem[] : [],
        configured: json.meta?.configured !== false,
      }
    },
  })

  const subtables = useMemo(() => data?.data ?? [], [data?.data])
  const configured = error ? false : (data?.configured ?? true)

  useEffect(() => {
    if (error) {
      message.error('加载成品检验子表失败')
      setSelectedEntityCode(undefined)
      return
    }
    if (subtables.length === 0) return
    if (!selectedEntityCode || !subtables.some((item) => item.entity_code === selectedEntityCode)) {
      setSelectedEntityCode(subtables[0]?.entity_code)
    }
  }, [subtables, selectedEntityCode, error, message])

  const selectedSubtable = useMemo(
    () => subtables.find((item) => item.entity_code === selectedEntityCode),
    [selectedEntityCode, subtables]
  )

  const resolvedDashboardContent = renderDashboardContent
    ? renderDashboardContent({ selectedEntityCode, subtables })
    : dashboardContent

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
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {resolvedDashboardContent}
        <div style={{ padding: 24, textAlign: 'center' }}>
          <Spin size="large" />
        </div>
      </div>
    )
  }

  if (!selectedEntityCode) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {resolvedDashboardContent}
        <div style={{ padding: 24 }}>
          <Alert
            title={configured ? '暂无可用子表' : '飞书数据源未配置'}
            description={
              configured
                ? '当前产品分组暂未返回可展示的子表。'
                : '请在左侧导航栏「质量管理 -> 飞书设置」中配置飞书应用凭证和实体映射。'
            }
            type={configured ? 'info' : 'warning'}
            showIcon
          />
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div ref={setToolbarContainer} />
      {resolvedDashboardContent}
      <InspectionFeishuTable
        title={title}
        listApi={recordsApi}
        pullApi={`/api/v1/quality/inspection-finished/${productGroup}/pull`}
        entityCode={selectedEntityCode}
        autoColumnPreset="finished"
        toolbarContent={toolbarContent}
        toolbarContainer={toolbarContainer}
        editable
      />
    </div>
  )
}
