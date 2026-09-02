'use client'

import { Empty } from 'antd'
import type { ReactNode } from 'react'

interface TableEmptyStateProps {
  /** 是否存在筛选/搜索条件 */
  hasFilters?: boolean
  /** 是否处于加载失败（含无权限）状态 */
  hasError?: boolean
  /** 失败时的提示文案（如权限不足说明） */
  errorMessage?: string
}

/**
 * 表格空数据三区分（DESIGN.md §5）：
 * - 加载失败/无权限：明确说明原因，不伪装成空数据
 * - 存在筛选条件：提示「当前筛选无结果」
 * - 无筛选条件：提示「尚未创建数据」
 */
export function TableEmptyState({
  hasFilters = false,
  hasError = false,
  errorMessage = '数据加载失败，请稍后重试或联系管理员',
}: TableEmptyStateProps): ReactNode {
  let description = '尚未创建数据'
  if (hasError) {
    description = errorMessage
  } else if (hasFilters) {
    description = '当前筛选条件下无匹配数据'
  }
  return (
    <Empty
      image={Empty.PRESENTED_IMAGE_SIMPLE}
      description={description}
      style={{ padding: '24px 0' }}
    />
  )
}
