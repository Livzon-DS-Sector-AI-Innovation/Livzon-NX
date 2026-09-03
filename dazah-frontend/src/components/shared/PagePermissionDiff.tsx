'use client'

import { Alert, Table } from 'antd'
import type { PageGrantChange } from '@/lib/page-permission-editor'

export function PagePermissionDiff({ changes }: { changes: PageGrantChange[] }) {
  return <div className="space-y-3">
    <Alert type="warning" showIcon message={`即将调整 ${changes.length} 个页面的授权`}
      description="发布模块的权限调整保存后立即生效，相关 Livzon 访问范围将过期。请核对新增权限、撤销权限和数据范围。" />
    <Table size="small" rowKey="pageKey" dataSource={changes} pagination={false}
      scroll={{ y: 360, x: 680 }} columns={[
        { title: '菜单页面', dataIndex: 'pageName', width: 190 },
        { title: '调整前', dataIndex: 'before', width: 245 },
        { title: '调整后', dataIndex: 'after', width: 245 },
      ]} />
  </div>
}
