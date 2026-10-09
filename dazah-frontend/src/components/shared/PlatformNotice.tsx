'use client'

import { useState } from 'react'
import { Alert, Button, Modal, Typography, theme } from 'antd'
import type { AlertProps } from 'antd'
import { ArrowUpOutlined } from '@ant-design/icons'
import styles from './PlatformNotice.module.css'

export interface PlatformNoticeProps extends AlertProps {
  /** A page may reuse an existing rule dialog. This callback must not write data. */
  onLearnRules?: () => void
  rulesDisabled?: boolean
  /** 数据提醒类提示可关闭「了解访问规则」入口；默认保持原行为 */
  showRulesLink?: boolean
}

/** Platform-wide notices keep the summary visible and open complete details on demand. */
export default function PlatformNotice({
  title,
  message,
  description,
  action,
  type = 'info',
  className,
  style,
  onLearnRules,
  rulesDisabled = false,
  showRulesLink = true,
  ...alertProps
}: PlatformNoticeProps) {
  const [rulesOpen, setRulesOpen] = useState(false)
  const { token } = theme.useToken()
  const heading = title ?? message
  const colors = {
    info: { background: token.colorInfoBg, color: token.colorInfo },
    success: { background: token.colorSuccessBg, color: token.colorSuccess },
    warning: { background: token.colorWarningBg, color: token.colorWarning },
    error: { background: token.colorErrorBg, color: token.colorError },
  }[type]

  return <>
    <Alert {...alertProps} type={type} banner={false} showIcon icon={undefined}
      className={`${styles.notice} ${className || ''}`} data-platform-notice={type}
      style={{ ...style, background: colors.background, borderColor: 'transparent', borderRadius: token.borderRadiusLG, color: token.colorText }}
      title={<span className={styles.summary}>{heading}</span>}
      action={<div className={styles.actions}>
        {action}
        {showRulesLink && (
          <Button type="link" className={styles.rulesButton} style={{ color: colors.color }}
            disabled={rulesDisabled} onClick={onLearnRules || (() => setRulesOpen(true))}>
            了解访问规则 <ArrowUpOutlined rotate={45} aria-hidden />
          </Button>
        )}
      </div>} />
    <Modal title="访问规则与提示说明" open={rulesOpen} centered width={640} destroyOnHidden
      onCancel={() => setRulesOpen(false)}
      footer={<Button type="primary" onClick={() => setRulesOpen(false)}>我知道了</Button>}>
      <div className={styles.details}>
        <Typography.Paragraph strong>{heading}</Typography.Paragraph>
        {description && <div className={styles.description}>{description}</div>}
        <Typography.Paragraph type="secondary" className={styles.accessNote}>
          页面访问与操作需获得相应授权。本入口仅查看说明，不修改权限或业务数据。
        </Typography.Paragraph>
      </div>
    </Modal>
  </>
}
