import { redirect } from 'next/navigation'

// 旧路由兼容：合同审批结果已迁移至合同管理子路由
export default function ContractApprovalResultsRedirect() {
  redirect('/hr/contracts/approval-results')
}
