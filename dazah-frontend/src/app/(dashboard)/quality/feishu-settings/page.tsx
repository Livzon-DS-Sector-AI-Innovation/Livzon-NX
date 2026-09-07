import { redirect } from 'next/navigation'

// 「飞书设置」已升级为「质量设置」（含飞书设置 / 通知设置两个 Tab）
export default function QualityFeishuSettingsRoutePage() {
  redirect('/quality/settings')
}
