import Image from 'next/image'
import type { ReactNode } from 'react'
import { DeploymentUnitOutlined, SafetyCertificateOutlined, SettingOutlined } from '@ant-design/icons'
import { AntdProvider } from '@/components/AntdProvider'

import styles from './AuthLayout.module.css'

interface AuthLayoutProps {
  children: ReactNode
  footerText?: string
}
export function AuthLayout({
  children,
  footerText = '仅限已授权人员使用',
}: AuthLayoutProps) {
  return (
    <AntdProvider fixedAppearance="light"><main className={styles.authPage} data-appearance="fixed-light">
      <section className={styles.brandPane} aria-label="平台介绍">
        <div className={styles.brandContent}>
          <div className={styles.brand}>
            <span className={styles.brandMark}>
              <Image
                src="/brand/livzon-mark.png"
                alt=""
                width={44}
                height={44}
                priority
              />
            </span>
            <span className={styles.brandName}>LIVZON</span>
            <span className={styles.brandTagline}>科技赋能制药 守护人类健康</span>
          </div>

          <div className={styles.brandMessage}>
            <h1>原料药工厂管理平台</h1>
            <div className={styles.brandSubtitle}>FACTORY MANAGEMENT PLATFORM</div>
            <p>
              统一承载生产、质量、设备与安全业务，<br />帮助工厂团队清晰、高效地完成日常管理工作。
            </p>
            <ul className={styles.brandFeatures} aria-label="平台业务能力">
              <li><span aria-hidden="true"><DeploymentUnitOutlined /></span><div><strong>生产协同</strong><small>计划 · 执行 · 可视</small></div></li>
              <li><span aria-hidden="true"><SafetyCertificateOutlined /></span><div><strong>质量管控</strong><small>合规 · 追溯 · 闭环</small></div></li>
              <li><span aria-hidden="true"><SettingOutlined /></span><div><strong>设备与安全</strong><small>稳定 · 高效 · 安全</small></div></li>
            </ul>
          </div>

          <p className={styles.brandFootnote}>LIVZON<br />FACTORY MANAGEMENT PLATFORM</p>
        </div>
      </section>

      <section className={styles.accessPane} aria-label="身份认证">
        <p className={styles.accessValues}>高效 · 合规 · 安全 · 可持续</p>
        <div className={styles.mobileBrand}>
          <Image
            src="/brand/livzon-mark.png"
            alt=""
            width={32}
            height={32}
            priority
          />
          <div>
            <strong>LIVZON</strong>
            <span>原料药工厂管理平台</span>
          </div>
        </div>

        <div className={styles.accessContent}>{children}</div>
        <p className={styles.accessFooter}>{footerText}</p>
      </section>
    </main></AntdProvider>
  )
}
