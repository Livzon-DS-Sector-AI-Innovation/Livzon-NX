import Image from 'next/image'
import type { ReactNode } from 'react'

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
    <main className={styles.authPage}>
      <section className={styles.brandPane} aria-label="平台介绍">
        <div className={styles.brandGlow} aria-hidden="true" />
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
          </div>

          <div className={styles.brandMessage}>
            <span className={styles.internalBadge}>内部系统</span>
            <h1>原料药工厂管理平台</h1>
            <p>
              统一承载生产、质量、设备与安全业务，帮助工厂团队清晰、高效地完成日常管理工作。
            </p>
          </div>

          <p className={styles.brandFootnote}>Factory Management Platform</p>
        </div>
      </section>

      <section className={styles.accessPane} aria-label="身份认证">
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
    </main>
  )
}
