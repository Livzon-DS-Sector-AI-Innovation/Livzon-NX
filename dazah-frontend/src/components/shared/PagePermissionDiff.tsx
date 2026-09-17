'use client'

import type { ReactNode } from 'react'
import { Alert, Table, Tag } from 'antd'
import type { PageGrantChange, PageGrantChangeKind } from '@/lib/page-permission-editor'

const changeKinds: Record<PageGrantChangeKind, { label: string; color: string }> = {
  grant: { label: '新增授权', color: 'green' },
  expand: { label: '扩大权限', color: 'gold' },
  restrict: { label: '收紧权限', color: 'orange' },
  revoke: { label: '撤销授权', color: 'red' },
  mixed: { label: '组合调整', color: 'blue' },
  source: { label: '来源变化', color: 'default' },
}

export function PagePermissionDiff({ changes, impactNote }: {
  changes: PageGrantChange[]
  impactNote?: ReactNode
}) {
  const counts = changes.reduce<Partial<Record<PageGrantChangeKind, number>>>((result, change) => {
    result[change.kind] = (result[change.kind] || 0) + 1
    return result
  }, {})
  return <div className="space-y-3">
    <Alert type="warning" showIcon message={`即将调整 ${changes.length} 个页面的授权`}
      description={<div className="space-y-2">
        <div>保存后立即生效，相关 Livzon 访问范围将过期。请重点核对扩大、收紧和撤销授权。</div>
        <div className="flex flex-wrap gap-2">{Object.entries(counts).map(([kind, count]) => {
          const item = changeKinds[kind as PageGrantChangeKind]
          return <Tag key={kind} color={item.color}>{item.label} {count}</Tag>
        })}</div>
        {impactNote && <div>{impactNote}</div>}
      </div>} />
    <Table size="small" rowKey="pageKey" dataSource={changes} pagination={false}
      scroll={{ y: 360, x: 680 }} columns={[
        { title: '菜单页面', dataIndex: 'pageName', width: 190 },
        { title: '影响', dataIndex: 'kind', width: 100,
          render: (kind: PageGrantChangeKind) => <Tag color={changeKinds[kind].color}>{changeKinds[kind].label}</Tag> },
        { title: '调整前', dataIndex: 'before', width: 245 },
        { title: '调整后', dataIndex: 'after', width: 245 },
      ]} />
  </div>
}
