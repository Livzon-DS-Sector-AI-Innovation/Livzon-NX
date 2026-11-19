import { MappedDatasetPage } from '@/components/feishu-data'
import { ADMIN_SEALS_PAGE_KEY } from '@/lib/administration-pages'

export default function SealsPage() {
  return (
    <MappedDatasetPage
      moduleCode="administration"
      pageKey={ADMIN_SEALS_PAGE_KEY}
      title="印章管理"
      enableAdvancedQuery={false}
      enablePersonAvatars
      // 审批人/审批状态列只在点行后的详情里看，表格保持精简
      hiddenFieldNames={[
        '分管领导',
        '财务总监',
        '部门负责人',
        '财务总监审批',
        '分管领导审批',
        '部门负责人审批',
        '审批状态',
      ]}
    />
  )
}
