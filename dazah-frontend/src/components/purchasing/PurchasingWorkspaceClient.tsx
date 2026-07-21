'use client'

import Link from 'next/link'
import { Button, Tag } from 'antd'
import {
  AuditOutlined,
  FileExcelOutlined,
  FileProtectOutlined,
  FileSearchOutlined,
  FormOutlined,
  PlusOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
  ShopOutlined,
  SolutionOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'
import type { PurchaseRequestCategory } from '@/types/purchasing'
import {
  purchaseCategories,
  purchaseCategoryLabels,
} from './purchaseRequestConstants'

type WorkspaceAction = {
  title: string
  description: string
  href: string
  icon: ReactNode
  tag: string
}

type ProcessStep = {
  title: string
  description: string
}

const commonActions: WorkspaceAction[] = [
  {
    title: '采购申请',
    description: '按物料类别填写申购部门、申请日期和明细。',
    href: '#request-categories',
    icon: <FormOutlined />,
    tag: '七类申请',
  },
  {
    title: '采购审批',
    description: '进入部门负责人或分管领导审批待处理申请。',
    href: '/purchasing/approval/hardware/department-head',
    icon: <AuditOutlined />,
    tag: '流程处理',
  },
  {
    title: '采购订单',
    description: '月度汇总与 Excel 导出。',
    href: '/purchasing/order',
    icon: <FileExcelOutlined />,
    tag: '已通过申请',
  },
  {
    title: '发票识别',
    description: '上传发票文件，识别并管理明细记录。',
    href: '/purchasing/invoice-recognition',
    icon: <FileSearchOutlined />,
    tag: '票据处理',
  },
]

const secondaryActions: WorkspaceAction[] = [
  {
    title: '供应商管理',
    description: '导入供应商清单并按文件字段展示检索。',
    href: '/purchasing/supplier',
    icon: <ShopOutlined />,
    tag: '主数据',
  },
  {
    title: '合同汇总',
    description: '查看采购合同汇总信息。',
    href: '/purchasing/contract-summary',
    icon: <FileProtectOutlined />,
    tag: '合同',
  },
  {
    title: '合同生成',
    description: '按固定资产、耗材、五金和原材料生成合同。',
    href: '/purchasing/contract-generation/fixed-assets',
    icon: <SolutionOutlined />,
    tag: '模板',
  },
]

const categoryDescriptions: Record<PurchaseRequestCategory, string> = {
  hardware: '五金材料申购',
  computer: '电脑材料申购',
  office: '办公用品申购',
  'raw-auxiliary': '原辅料申购',
  'chemical-glass': '化玻申购',
  electrical: '电器申购',
  'labor-protection': '劳保申购',
}

const processSteps: ProcessStep[] = [
  {
    title: '申请填写',
    description: '按类别录入申购部门和明细。',
  },
  {
    title: '部门负责人审批',
    description: '确认部门需求和申请内容。',
  },
  {
    title: '分管领导审批',
    description: '完成最终审批流转。',
  },
  {
    title: '订单汇总',
    description: '按月汇总已通过申请。',
  },
  {
    title: '发票/合同处理',
    description: '衔接票据识别和合同生成。',
  },
]

export function PurchasingWorkspaceClient() {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-[13px] text-[var(--color-stone)]">
            采购管理
          </p>
          <h1 className="mb-2 text-[22px] font-semibold text-[var(--color-charcoal)]">
            采购管理工作台
          </h1>
          <p className="max-w-[720px] text-[14px] leading-6 text-[var(--color-steel)]">
            集中处理采购申请、审批、订单汇总、发票识别与合同生成。
          </p>
        </div>
        <Button type="primary" href="#request-categories" icon={<PlusOutlined />}>
          新建采购申请
        </Button>
      </div>

      <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)]">
        <div className="border-b border-[var(--color-hairline)] bg-[var(--color-surface-soft)] px-4 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)]">
                常用操作
              </h2>
              <p className="mt-1 text-[13px] text-[var(--color-stone)]">
                从高频入口开始处理采购日常工作。
              </p>
            </div>
            <Tag color="processing">工作台入口</Tag>
          </div>
        </div>
        <div className="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-4">
          {commonActions.map((action) => (
            <Link
              key={action.title}
              href={action.href}
              className="group flex min-h-[152px] flex-col justify-between rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4 transition-colors hover:border-[var(--color-hairline-strong)]"
            >
              <div>
                <div className="mb-4 flex items-start justify-between gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-[8px] bg-[var(--color-surface)] text-[18px] text-[var(--color-primary)]">
                    {action.icon}
                  </span>
                  <Tag>{action.tag}</Tag>
                </div>
                <h3 className="text-[15px] font-semibold text-[var(--color-charcoal)]">
                  {action.title}
                </h3>
                <p className="mt-2 text-[13px] leading-5 text-[var(--color-steel)]">
                  {action.description}
                </p>
              </div>
              <span className="mt-4 inline-flex items-center gap-1 text-[13px] font-medium text-[var(--color-primary)]">
                进入
                <RightOutlined className="text-[10px]" />
              </span>
            </Link>
          ))}
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section
          id="request-categories"
          className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)]"
        >
          <div className="border-b border-[var(--color-hairline)] bg-[var(--color-surface-soft)] px-4 py-4">
            <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)]">
              申请类别
            </h2>
            <p className="mt-1 text-[13px] text-[var(--color-stone)]">
              按采购内容选择对应申请表。
            </p>
          </div>
          <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
            {purchaseCategories.map((category) => (
              <Link
                key={category}
                href={`/purchasing/request/${category}`}
                className="flex min-h-[104px] items-start justify-between gap-3 rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4 transition-colors hover:border-[var(--color-hairline-strong)]"
              >
                <div>
                  <h3 className="text-[15px] font-semibold text-[var(--color-charcoal)]">
                    {purchaseCategoryLabels[category]}
                  </h3>
                  <p className="mt-2 text-[13px] text-[var(--color-steel)]">
                    {categoryDescriptions[category]}
                  </p>
                </div>
                <RightOutlined className="mt-1 text-[12px] text-[var(--color-stone)]" />
              </Link>
            ))}
          </div>
        </section>

        <aside className="space-y-5">
          <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)]">
            <div className="border-b border-[var(--color-hairline)] bg-[var(--color-surface-soft)] px-4 py-4">
              <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)]">
                采购流程
              </h2>
              <p className="mt-1 text-[13px] text-[var(--color-stone)]">
                从申请到采购执行的主要节点。
              </p>
            </div>
            <ol className="space-y-0 p-4">
              {processSteps.map((step, index) => (
                <li key={step.title} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--color-surface)] text-[12px] font-semibold text-[var(--color-charcoal)]">
                      {index + 1}
                    </span>
                    {index < processSteps.length - 1 && (
                      <span className="h-9 w-px bg-[var(--color-hairline)]" />
                    )}
                  </div>
                  <div className="pb-4">
                    <h3 className="text-[14px] font-semibold text-[var(--color-charcoal)]">
                      {step.title}
                    </h3>
                    <p className="mt-1 text-[13px] leading-5 text-[var(--color-steel)]">
                      {step.description}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </section>

          <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4">
            <div className="mb-3 flex items-center gap-2">
              <SafetyCertificateOutlined className="text-[18px] text-[var(--color-primary)]" />
              <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)]">
                其他入口
              </h2>
            </div>
            <div className="space-y-3">
              {secondaryActions.map((action) => (
                <Link
                  key={action.title}
                  href={action.href}
                  className="flex items-start justify-between gap-3 rounded-[8px] border border-[var(--color-hairline)] p-3 transition-colors hover:border-[var(--color-hairline-strong)]"
                >
                  <div>
                    <h3 className="text-[14px] font-medium text-[var(--color-charcoal)]">
                      {action.title}
                    </h3>
                    <p className="mt-1 text-[12px] leading-5 text-[var(--color-stone)]">
                      {action.description}
                    </p>
                  </div>
                  <RightOutlined className="mt-1 text-[11px] text-[var(--color-stone)]" />
                </Link>
              ))}
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}
