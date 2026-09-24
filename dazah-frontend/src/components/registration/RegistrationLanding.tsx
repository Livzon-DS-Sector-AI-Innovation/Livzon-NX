'use client'

import {
  AuditOutlined,
  BookOutlined,
  DollarOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import { ModuleLandingCards, type ModuleLandingEntry } from '@/components/shared/ModuleLandingCards'

const entries: ModuleLandingEntry[] = [
  { title: '申报项目', description: '项目概览、申报台账与申报进度', href: '/registration/project', icon: <FileSearchOutlined />, dashboard: true },
  { title: '授权书管理', description: '授权书台账、FDA 信息和资料下载', href: '/registration/authorization-letter', icon: <FileTextOutlined /> },
  { title: '证书管理', description: '证书概览、有效期与到期提醒', href: '/registration/certificate-management', icon: <SafetyCertificateOutlined />, dashboard: true },
  { title: '法规跟踪', description: '近期国内外法规更新', href: '/registration/regulation', icon: <AuditOutlined /> },
  { title: '注册费用', description: '注册相关费用统计与台账', href: '/registration/fees', icon: <DollarOutlined />, dashboard: true },
  { title: '注册知识库', description: '法规解读、申报经验和常见问题', href: '/registration/knowledge', icon: <BookOutlined /> },
]

export function RegistrationLanding() {
  return <ModuleLandingCards title="注册管理" description="查看申报进展、证书状态与注册业务入口" entries={entries} />
}
