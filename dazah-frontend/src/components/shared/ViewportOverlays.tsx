'use client'

import type { ReactNode } from 'react'
import { App, ConfigProvider } from 'antd'
import styles from './viewport-overlays.module.css'

/** Apply viewport bounds to business overlays, including their body portals. */
export default function ViewportOverlays({ children }: { children: ReactNode }) {
  return (
    <ConfigProvider
      modal={{ centered: true, classNames: { root: styles.modal, container: styles.container, title: styles.title, body: styles.body, footer: styles.footer } }}
      drawer={{ classNames: { body: styles.drawerBody, title: styles.title, footer: styles.footer } }}
      popconfirm={{ classNames: { root: styles.floating } }}
      popover={{ classNames: { root: styles.floating } }}
      datePicker={{ classNames: { popup: { root: styles.datePicker } } }}
      timePicker={{ classNames: { popup: { root: styles.datePicker } } }}
      select={{ classNames: { popup: { root: styles.select } } }}
      dropdown={{ classNames: { root: styles.dropdown } }}
    >
      <App>{children}</App>
    </ConfigProvider>
  )
}
