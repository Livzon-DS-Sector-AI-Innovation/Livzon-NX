'use client'

import {
  AlertOutlined,
  ApartmentOutlined,
  AuditOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  NotificationOutlined,
  RollbackOutlined,
  SafetyCertificateOutlined,
  SafetyOutlined,
  SettingOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { ModuleLandingCards, type ModuleLandingEntry } from '@/components/shared/ModuleLandingCards'

const entries: ModuleLandingEntry[] = [
  { title: '文件管理', description: '按部门浏览和管理文件目录', href: '/quality/documents', icon: <FolderOpenOutlined /> },
  { title: '偏差管理', description: '偏差统计、报告记录与处理进度', href: '/quality/deviations', icon: <FileTextOutlined />, dashboard: true },
  { title: 'CAPA管理', description: '纠正预防措施统计与计划跟踪', href: '/quality/capas', icon: <SafetyCertificateOutlined />, dashboard: true },
  { title: '投诉管理', description: '客户投诉台账和处理记录', href: '/quality/complaints', icon: <NotificationOutlined /> },
  { title: '质量检验', description: '物品、仪器和成品检验入口', href: '/quality/inspection', icon: <ExperimentOutlined /> },
  { title: 'OOS/OOT管理', description: '报告记录、调查推送及台账', href: '/quality/oos-oot', icon: <WarningOutlined /> },
  { title: '产品质量', description: '产品质量标准与回顾', href: '/quality/product-quality', icon: <DatabaseOutlined /> },
  { title: '成品异常报告', description: '成品异常统计与年度明细', href: '/quality/anomaly-report', icon: <AlertOutlined />, dashboard: true },
  { title: '退货召回', description: '退货申请与退货台账', href: '/quality/return-recalls', icon: <RollbackOutlined /> },
  { title: '供应商管理', description: '供应商资质状态与台账', href: '/quality/suppliers', icon: <ApartmentOutlined />, dashboard: true },
  { title: '变更控制', description: '变更台账与行动计划概览', href: '/quality/change', icon: <AuditOutlined />, dashboard: true },
  { title: '验证与确认', description: '验证计划和执行概览', href: '/quality/validation', icon: <SafetyOutlined />, dashboard: true },
  { title: '质量设置', description: '数据同步映射与通知设置', href: '/quality/settings', icon: <SettingOutlined /> },
]

export function QualityLanding() {
  return <ModuleLandingCards title="质量管理" description="查看质量状态、风险与业务入口" entries={entries} />
}
