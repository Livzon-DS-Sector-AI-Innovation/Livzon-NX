'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, App, Select, Space, Spin, Tag } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'next/navigation'

import { fetchInspectionMaterials } from '@/lib/api/client/quality'
import type { InspectionMaterialItem } from '@/types/quality'
import { InspectionFeishuTable } from './InspectionFeishuTable'

interface InspectionMaterialPageProps {
  module: 'solid' | 'liquid'
}

const MODULE_TITLES: Record<string, string> = {
  solid: '固体物料检验',
  liquid: '液体物料检验',
}

/**
 * 固体/液体物料检验单页：顶部「物料筛选」按模块列出全部物料（类似验证模块年份筛选），
 * 选中即加载该物料的检验表；支持提交后跳转（recordId/entityCode）自动定位并弹详情。
 */
export function InspectionMaterialPage({ module }: InspectionMaterialPageProps) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const searchParams = useSearchParams()
  const [selectedEntityCode, setSelectedEntityCode] = useState<string>()
  const pulledForRef = useRef<string | null>(null)

  const {
    data: materials = [],
    isLoading: loading,
    error,
    refetch,
  } = useQuery<InspectionMaterialItem[]>({
    queryKey: ['quality-inspection', 'materials', module],
    queryFn: async () => {
      const all = await fetchInspectionMaterials()
      return all.filter((item) => item.module === module)
    },
  })

  // 新建提交后跳转携带的查询参数：recordId + entityCode
  const highlightRecordId = searchParams.get('recordId')
  const highlightEntityCode = searchParams.get('entityCode')

  useEffect(() => {
    if (error) {
      message.error(`加载${MODULE_TITLES[module]}物料失败`)
      setSelectedEntityCode(undefined)
      return
    }
    if (materials.length === 0) return
    // 跳转详情时优先切到对应物料
    if (
      highlightEntityCode &&
      materials.some((item) => item.entity_code === highlightEntityCode)
    ) {
      setSelectedEntityCode(highlightEntityCode)
      return
    }
    if (
      !selectedEntityCode ||
      !materials.some((item) => item.entity_code === selectedEntityCode)
    ) {
      setSelectedEntityCode(materials[0]?.entity_code)
    }
  }, [materials, selectedEntityCode, error, message, module, highlightEntityCode])

  const selectedMaterial = useMemo(
    () => materials.find((item) => item.entity_code === selectedEntityCode),
    [materials, selectedEntityCode]
  )

  // group_key 与后端 MATERIAL_GROUP_ENTITY_MAP 同源，records/pull 端点校验必过
  const recordsApi = selectedMaterial
    ? `/api/v1/quality/inspection-${module}/${selectedMaterial.group_key}/records`
    : undefined
  const pullApi = selectedMaterial
    ? `/api/v1/quality/inspection-${module}/${selectedMaterial.group_key}/pull`
    : undefined

  // 提交后跳转：静默回拉一次镜像，让新记录尽快出现在列表（best-effort），随后刷新列表
  useEffect(() => {
    if (!highlightRecordId || !pullApi || pulledForRef.current === highlightRecordId) return
    pulledForRef.current = highlightRecordId
    fetch(pullApi, { method: 'POST' })
      .catch(() => undefined)
      .finally(() =>
        queryClient.invalidateQueries({ queryKey: ['quality-inspection', 'list', recordsApi] })
      )
  }, [highlightRecordId, pullApi, recordsApi, queryClient])

  const materialOptions = useMemo(() => {
    const grouped = new Map<string, InspectionMaterialItem[]>()
    for (const item of materials) {
      const label = item.group_label || item.group_key || '其他'
      const list = grouped.get(label) ?? []
      list.push(item)
      grouped.set(label, list)
    }
    return Array.from(grouped.entries()).map(([label, items]) => ({
      label,
      options: items.map((item) => ({
        value: item.entity_code,
        label: item.label,
      })),
    }))
  }, [materials])

  const toolbarContent = (
    <Space wrap>
      <span style={{ fontSize: 13, color: 'rgba(0, 0, 0, 0.65)' }}>物料筛选</span>
      <Select
        showSearch
        value={selectedEntityCode}
        placeholder="输入物料名称或代码搜索"
        loading={loading}
        style={{ width: 320 }}
        options={materialOptions}
        filterOption={(input, option) => String(option?.label ?? '').includes(input)}
        onChange={setSelectedEntityCode}
      />
      {selectedMaterial ? <Tag color="blue">{selectedMaterial.label}</Tag> : null}
    </Space>
  )

  if (loading && materials.length === 0) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!selectedEntityCode || !recordsApi) {
    return (
      <div style={{ padding: 24 }}>
        <Alert
          title={error ? '物料列表加载失败' : '暂无可用物料'}
          description={
            error
              ? '未获取到该模块的物料列表，请稍后重试。'
              : `当前模块暂未返回可展示的${MODULE_TITLES[module]}物料。`
          }
          type={error ? 'error' : 'info'}
          showIcon
          action={<a onClick={() => void refetch()}>重试</a>}
        />
      </div>
    )
  }

  return (
    <InspectionFeishuTable
      title={MODULE_TITLES[module]}
      listApi={recordsApi}
      pullApi={pullApi}
      entityCode={selectedEntityCode}
      toolbarContent={toolbarContent}
      editable
      createWithMaterialPicker
      materialPickerModule={module}
      highlightRecordId={highlightRecordId}
      highlightEntityCode={highlightEntityCode}
      enableAttachmentPreview
    />
  )
}
