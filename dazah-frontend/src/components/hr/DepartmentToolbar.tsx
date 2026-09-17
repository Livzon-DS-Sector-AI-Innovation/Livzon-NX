'use client'

import { Space, Button, Segmented } from 'antd'
import {
  PlusOutlined,
  SyncOutlined,
  UnorderedListOutlined,
  ApartmentOutlined,
} from '@ant-design/icons'

interface DepartmentToolbarProps {
  activeView: 'table' | 'tree'
  onViewChange: (view: 'table' | 'tree') => void
  canEdit: boolean
  canSync: boolean
  onAdd: () => void
  onSync: () => void
  syncing: boolean
}

export default function DepartmentToolbar({
  activeView,
  onViewChange,
  canEdit,
  canSync,
  onAdd,
  onSync,
  syncing,
}: DepartmentToolbarProps) {
  return (
    <div className="flex items-center justify-between">
      <Segmented
        value={activeView}
        onChange={(value) => onViewChange(value as 'table' | 'tree')}
        options={[
          { label: '表格视图', value: 'table', icon: <UnorderedListOutlined /> },
          { label: '组织架构树', value: 'tree', icon: <ApartmentOutlined /> },
        ]}
      />

      {(canEdit || canSync) && (
        <Space>
          {canEdit && <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={onAdd}
          >
            新增部门
          </Button>}
          {canSync && <Button
            icon={<SyncOutlined spin={syncing} />}
            onClick={onSync}
            loading={syncing}
          >
            从飞书同步
          </Button>}
        </Space>
      )}
    </div>
  )
}
