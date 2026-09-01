'use client'

import { Tabs } from 'antd'

import { ModuleFeishuDataSourcePage } from '@/components/feishu-data'
import {
  createWarehouseFeishuRootAction,
  deleteWarehouseFeishuRootAction,
  discoverWarehouseFeishuRootAction,
  saveWarehouseFeishuConfigAction,
  saveWarehousePageBindingsAction,
  syncWarehouseFeishuTableAction,
  syncWarehouseFeishuTablesAction,
  testWarehouseFeishuConfigAction,
} from '@/actions/warehouse'
import { WarehouseFeishuConfigPage } from './WarehouseFeishuConfigPage'

interface WarehouseSettingsTabsProps {
  initialConfigs: import('@/types/warehouse').WarehousePageFeishuConfig[]
}

/**
 * 仓储设置合并页：页面映射（每页 app_token/table_id 快捷映射）
 * 与飞书数据源（应用凭据 + 页面数据表映射发布）二合一。
 * 入口发现 / 资源目录区块对仓储日常冗余，默认不展示。
 */
export function WarehouseSettingsTabs({ initialConfigs }: WarehouseSettingsTabsProps) {
  return (
    <Tabs
      defaultActiveKey="page-mapping"
      items={[
        {
          key: 'page-mapping',
          label: '页面映射',
          children: <WarehouseFeishuConfigPage initialConfigs={initialConfigs} />,
        },
        {
          key: 'feishu-data-source',
          label: '飞书数据源',
          children: (
            <ModuleFeishuDataSourcePage
              moduleCode="warehouse"
              showRootsAndCatalog={false}
              writeActions={{
                saveConfig: saveWarehouseFeishuConfigAction,
                testConfig: testWarehouseFeishuConfigAction,
                createRoot: createWarehouseFeishuRootAction,
                deleteRoot: deleteWarehouseFeishuRootAction,
                discoverRoot: discoverWarehouseFeishuRootAction,
                syncResource: syncWarehouseFeishuTableAction,
                syncResources: syncWarehouseFeishuTablesAction,
                saveBindings: saveWarehousePageBindingsAction,
              }}
            />
          ),
        },
      ]}
    />
  )
}
