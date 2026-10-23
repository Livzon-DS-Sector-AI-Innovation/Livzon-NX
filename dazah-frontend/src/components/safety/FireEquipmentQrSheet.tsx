'use client'

import { PrinterOutlined } from '@ant-design/icons'
import { Button, Empty, Modal, Typography } from 'antd'
import { QRCodeSVG } from 'qrcode.react'

const { Text, Title } = Typography

export interface FireEquipmentQrItem {
  id: string
  equipmentTypeLabel: string
  equipmentNo: string
  department: string
  location: string
}

interface Props {
  open: boolean
  onClose: () => void
  /** 单台打印传一条，批量打印传过滤后的全部器材。 */
  items: FireEquipmentQrItem[]
}

/** 扫码点检地址：与前端路由 /safety/fire-inspection/scan/[equipment_id] 一致。 */
export function fireEquipmentScanUrl(equipmentId: string): string {
  if (typeof window === 'undefined') return ''
  return `${window.location.origin}/safety/fire-inspection/scan/${equipmentId}`
}

function QrCard({ item }: { item: FireEquipmentQrItem }) {
  const url = fireEquipmentScanUrl(item.id)
  return (
    <div
      style={{
        width: 240,
        border: '1px dashed #bfbfbf',
        borderRadius: 8,
        padding: 12,
        textAlign: 'center',
        background: '#ffffff',
        color: 'rgba(0, 0, 0, 0.88)',
      }}
    >
      <Title level={5} style={{ marginBottom: 4 }}>
        {item.equipmentTypeLabel}点检卡
      </Title>
      <Text strong style={{ display: 'block', marginBottom: 8 }}>
        编号：{item.equipmentNo || '（未填编号）'}
      </Text>
      {url ? (
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <QRCodeSVG value={url} size={140} level="M" />
        </div>
      ) : null}
      <Text style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
        部门：{item.department || '—'}
      </Text>
      <Text style={{ display: 'block', fontSize: 12 }}>
        位置：{item.location || '—'}
      </Text>
      <Text type="secondary" style={{ fontSize: 11 }}>
        飞书扫码查看详情并点检（每月一次）
      </Text>
    </div>
  )
}

/** 器材二维码弹窗：支持单台查看打印与批量打印（A4 约每行 2~3 张可裁切）。 */
export default function FireEquipmentQrSheet({ open, onClose, items }: Props) {
  return (
    <Modal
      title={items.length > 1 ? `批量打印二维码（${items.length} 台）` : '器材点检二维码'}
      open={open}
      onCancel={onClose}
      width={720}
      footer={[
        <Button
          key="print"
          type="primary"
          icon={<PrinterOutlined />}
          disabled={!items.length}
          onClick={() => window.print()}
        >
          打印
        </Button>,
        <Button key="close" onClick={onClose}>
          关闭
        </Button>,
      ]}
    >
      {items.length === 0 ? (
        <Empty description="没有可打印的器材" />
      ) : (
        <div
          className="fire-qr-sheet"
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 12,
            justifyContent: 'center',
            maxHeight: 480,
            overflowY: 'auto',
            padding: 8,
          }}
        >
          {items.map((item) => (
            <QrCard key={item.id} item={item} />
          ))}
        </div>
      )}
      <style jsx global>{`
        @media print {
          body * {
            visibility: hidden;
          }
          .fire-qr-sheet,
          .fire-qr-sheet * {
            visibility: visible;
          }
          .fire-qr-sheet {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            max-height: none !important;
            overflow: visible !important;
          }
          .ant-modal-footer,
          .ant-modal-close {
            display: none !important;
          }
        }
      `}</style>
    </Modal>
  )
}
