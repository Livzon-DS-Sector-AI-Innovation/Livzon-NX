'use client'

import { Modal, Button, Typography } from 'antd'
import { QRCodeSVG } from 'qrcode.react'
import { PrinterOutlined } from '@ant-design/icons'

const { Text, Title } = Typography

interface Props {
  open: boolean
  onClose: () => void
}

export default function EmployeeQrCode({ open, onClose }: Props) {
  // 生成二维码 URL：如果当前是 localhost，替换为局域网 IP
  const fillUrl = (() => {
    if (typeof window === 'undefined') return ''
    const protocol = window.location.protocol
    const hostname = window.location.hostname
    const port = window.location.port || '3000'
    return `${protocol}//${hostname}:${port}/hr/employee-fill`
  })()

  const handlePrint = () => {
    window.print()
  }

  return (
    <Modal
      title="员工档案填写二维码"
      open={open}
      onCancel={onClose}
      footer={[
        <Button key="print" type="primary" icon={<PrinterOutlined />} onClick={handlePrint}>
          打印
        </Button>,
        <Button key="close" onClick={onClose}>关闭</Button>,
      ]}
      width={400}
      className="qr-modal"
    >
      <div className="flex flex-col items-center py-4 qr-print-area">
        <Title level={5} className="mb-2">扫码填写员工档案</Title>
        <Text type="secondary" className="mb-4 text-xs">手机扫码即可填写信息，提交后自动录入员工档案</Text>
        {fillUrl && (
          <div className="p-4 bg-white border border-gray-200 rounded-lg">
            <QRCodeSVG
              value={fillUrl}
              size={220}
              level="M"
              includeMargin
            />
          </div>
        )}
        <Text type="secondary" className="mt-4 text-xs break-all text-center" style={{ maxWidth: 300 }}>
          {fillUrl}
        </Text>
      </div>

      <style jsx global>{`
        @media print {
          body * { visibility: hidden; }
          .qr-print-area, .qr-print-area * { visibility: visible; }
          .qr-print-area { position: absolute; left: 50%; top: 20%; transform: translateX(-50%); }
          .ant-modal-footer, .ant-modal-close { display: none !important; }
        }
      `}</style>
    </Modal>
  )
}
