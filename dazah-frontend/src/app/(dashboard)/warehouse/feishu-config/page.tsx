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

export default function WarehouseFeishuConfigPage() {
  return (
    <ModuleFeishuDataSourcePage
      moduleCode="warehouse"
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
  )
}
