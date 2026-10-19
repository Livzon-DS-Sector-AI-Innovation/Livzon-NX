'use client'

import { useRef, useState, type ReactNode } from 'react'
import { App, Button, Modal, type ButtonProps } from 'antd'

interface ProductionConfirmButtonProps extends Omit<ButtonProps, 'title' | 'onClick'> {
  title: ReactNode
  description: ReactNode
  confirmText?: string
  onConfirm: () => Promise<boolean | void> | boolean | void
}

/** Confirmation stays independent of table scroll and the trigger's viewport edge. */
export default function ProductionConfirmButton({
  title, description, confirmText = '确认', onConfirm, children, ...buttonProps
}: ProductionConfirmButtonProps) {
  const { message } = App.useApp()
  const [open, setOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const submitting = useRef(false)

  const confirm = async () => {
    if (submitting.current) return
    submitting.current = true
    setPending(true)
    try {
      if (await onConfirm() !== false) setOpen(false)
    } catch {
      message.error('操作请求失败，请重试')
    } finally {
      submitting.current = false
      setPending(false)
    }
  }

  return (
    <>
      <Button {...buttonProps} onClick={() => setOpen(true)}>{children}</Button>
      <Modal
        title={title}
        open={open}
        centered
        width={480}
        style={{ maxWidth: 'calc(100vw - 32px)' }}
        styles={{ body: { overflowWrap: 'anywhere', maxHeight: '60dvh', overflowY: 'auto' } }}
        destroyOnHidden
        okText={confirmText}
        cancelText="取消"
        okButtonProps={{ danger: buttonProps.danger }}
        confirmLoading={pending}
        cancelButtonProps={{ disabled: pending }}
        closable={!pending}
        mask={{ closable: !pending }}
        keyboard={!pending}
        onOk={() => void confirm()}
        onCancel={() => { if (!submitting.current) setOpen(false) }}
      >
        {description}
      </Modal>
    </>
  )
}
