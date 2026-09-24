'use client'

import Link from 'next/link'
import {
  AuditOutlined,
  DatabaseOutlined,
  FileExcelOutlined,
  FileProtectOutlined,
  FileSearchOutlined,
  FormOutlined,
  RightOutlined,
  ShopOutlined,
  SolutionOutlined,
} from '@ant-design/icons'
import { ModuleLandingCards, type ModuleLandingEntry } from '@/components/shared/ModuleLandingCards'
import type { PurchaseRequestCategory } from '@/types/purchasing'
import {
  approvalRoleLabels,
  purchaseApprovalWorkflows,
  purchaseCategories,
  purchaseCategoryLabels,
} from './purchaseRequestConstants'

const entries: ModuleLandingEntry[] = [
  {
    title: '采购申请',
    description: '按采购类别选择申请表，填写申购部门和物料明细。',
    href: '#request-categories',
    icon: <FormOutlined />,
  },
  {
    title: '物料编码库',
    description: '查询和维护采购物料编码。',
    href: '/purchasing/material-library',
    icon: <DatabaseOutlined />,
  },
  {
    title: '采购审批',
    description: '按采购类型进入审批流程，处理待审批申请。',
    href: '/purchasing/approval/hardware/hardware-warehouse',
    icon: <AuditOutlined />,
  },
  {
    title: '供应商管理',
    description: '查看、检索和维护供应商资料。',
    href: '/purchasing/supplier',
    icon: <ShopOutlined />,
  },
  {
    title: '采购订单',
    description: '按月汇总已通过的申请并导出订单。',
    href: '/purchasing/order',
    icon: <FileExcelOutlined />,
  },
  {
    title: '发票识别',
    description: '上传发票文件，识别并管理明细记录。',
    href: '/purchasing/invoice-recognition',
    icon: <FileSearchOutlined />,
  },
  {
    title: '合同汇总',
    description: '查看采购合同汇总信息。',
    href: '/purchasing/contract-summary',
    icon: <FileProtectOutlined />,
  },
  {
    title: '合同生成',
    description: '按采购类别选择合同模板。',
    href: '/purchasing/contract-generation/fixed-assets',
    icon: <SolutionOutlined />,
  },
]

const categoryDescriptions: Record<PurchaseRequestCategory, string> = {
  hardware: '五金材料申购',
  computer: '电脑材料申购',
  office: '办公用品申购',
  'raw-auxiliary': '原辅料申购',
  'chemical-glass': '化玻申购',
  electrical: '电气申购',
  'advertising-printing': '广告/印刷申购',
  fire: '消防申购',
  packaging: '包材申购',
  'labor-special': '特防申购',
  'labor-miscellaneous': '杂品申购',
  urgent: '加急采购申请',
}

const processSteps = [
  { title: '申请填写', description: '按类别录入申购部门和明细。' },
  { title: '按类别审批', description: '不同采购类型进入对应的仓库、安全、部门和领导节点。' },
  { title: '订单汇总', description: '按月汇总已通过申请。' },
  { title: '发票/合同处理', description: '衔接票据识别和合同生成。' },
]

const approvalWorkflowSummaryCategories: Array<{
  label: string
  category: PurchaseRequestCategory
}> = [
  { label: '五金材料', category: 'hardware' },
  { label: '电气', category: 'electrical' },
  { label: '特防', category: 'labor-special' },
  { label: '加急单', category: 'urgent' },
  { label: '其他采购类型', category: 'office' },
]

export function PurchasingWorkspaceClient() {
  return (
    <div className="space-y-6">
      <ModuleLandingCards
        title="采购管理"
        description="集中处理采购申请、审批、订单、供应商与合同业务。"
        entries={entries}
      />

      <section id="request-categories" aria-labelledby="request-categories-title">
        <div className="mb-4">
          <h2 id="request-categories-title" className="text-[18px] font-semibold text-[var(--color-charcoal)]">
            申请类别
          </h2>
          <p className="mt-1 text-[13px] text-[var(--color-steel)]">按采购内容选择对应申请表。</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {purchaseCategories.map((category) => (
            <Link
              key={category}
              href={`/purchasing/request/${category}`}
              className="flex min-h-[104px] items-start justify-between gap-3 rounded-[var(--rounded-sm)] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4 transition-colors hover:border-[var(--color-hairline-strong)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]"
            >
              <div>
                <h3 className="text-[15px] font-semibold text-[var(--color-charcoal)]">
                  {purchaseCategoryLabels[category]}
                </h3>
                <p className="mt-2 text-[13px] text-[var(--color-steel)]">
                  {categoryDescriptions[category]}
                </p>
              </div>
              <RightOutlined aria-hidden="true" className="mt-1 text-[12px] text-[var(--color-stone)]" />
            </Link>
          ))}
        </div>
      </section>

      <details className="rounded-[var(--rounded-sm)] border border-[var(--color-hairline)] bg-[var(--color-canvas)]">
        <summary className="cursor-pointer px-4 py-3 text-[14px] font-medium text-[var(--color-charcoal)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]">
          采购流程说明
        </summary>
        <div className="border-t border-[var(--color-hairline)] px-4 py-4">
          <ol className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {processSteps.map((step, index) => (
              <li key={step.title}>
                <h3 className="text-[14px] font-semibold text-[var(--color-charcoal)]">
                  {index + 1}. {step.title}
                </h3>
                <p className="mt-1 text-[13px] leading-5 text-[var(--color-steel)]">{step.description}</p>
              </li>
            ))}
          </ol>
          <div className="mt-4 space-y-2 border-t border-[var(--color-hairline)] pt-4">
            {approvalWorkflowSummaryCategories.map(({ label, category }) => (
              <p key={category} className="text-[12px] leading-5 text-[var(--color-steel)]">
                <span className="font-medium text-[var(--color-charcoal)]">{label}：</span>
                {purchaseApprovalWorkflows[category]
                  .map((role) => approvalRoleLabels[role])
                  .join(' → ')}
              </p>
            ))}
          </div>
        </div>
      </details>
    </div>
  )
}
