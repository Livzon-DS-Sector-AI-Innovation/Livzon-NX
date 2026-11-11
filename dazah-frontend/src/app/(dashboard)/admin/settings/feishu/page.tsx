import {
  createAdministrationFeishuRootAction,
  deleteAdministrationFeishuRootAction,
  discoverAdministrationFeishuRootAction,
  saveAdministrationFeishuConfigAction,
  saveAdministrationPageBindingsAction,
  syncAdministrationFeishuResourceAction,
  syncAdministrationFeishuResourcesAction,
  testAdministrationFeishuConfigAction,
} from '@/actions/administration'
import { ModuleFeishuDataSourcePage } from '@/components/feishu-data'

/** 行政飞书设置：应用凭证、多维表格入口、数据表同步与页面绑定（写操作经 Server Actions）。 */
export default function AdministrationFeishuSettingsPage() {
  return (
    <ModuleFeishuDataSourcePage
      moduleCode="administration"
      writeActions={{
        saveConfig: saveAdministrationFeishuConfigAction,
        testConfig: testAdministrationFeishuConfigAction,
        createRoot: createAdministrationFeishuRootAction,
        deleteRoot: deleteAdministrationFeishuRootAction,
        discoverRoot: discoverAdministrationFeishuRootAction,
        syncResource: syncAdministrationFeishuResourceAction,
        syncResources: syncAdministrationFeishuResourcesAction,
        saveBindings: saveAdministrationPageBindingsAction,
      }}
    />
  )
}
