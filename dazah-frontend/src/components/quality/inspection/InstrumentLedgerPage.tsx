'use client'

import { useState } from 'react'
import { Button } from 'antd'
import { UploadOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'

import { InspectionFeishuTable } from '@/components/quality/inspection'
import { InstrumentImportDrawer } from '@/components/quality/inspection/InstrumentImportDrawer'

/** 仪器台账页：通用飞书表 + 批量导入（预览/确认写飞书）。 */
export function InstrumentLedgerPage() {
  const queryClient = useQueryClient()
  const [importOpen, setImportOpen] = useState(false)

  const handleImportSuccess = () => {
    queryClient.invalidateQueries({ queryKey: ['quality-inspection', 'list'] })
    queryClient.invalidateQueries({ queryKey: ['quality-instruments', 'dashboard'] })
  }

  return (
    <>
      <InspectionFeishuTable
        title="仪器台账"
        listApi="/api/v1/quality/instruments/equipment"
        pullApi="/api/v1/quality/instruments/equipment/pull"
        entityCode="qc_instr_equipment"
        editable
        editablePersonFields
        enableEquipmentProfile
        enableAttachmentPreview
        showLastSyncTime
        toolbarContent={
          <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>
            批量导入
          </Button>
        }
        filters={[
          { key: '设备类型', label: '设备类型' },
          { key: '设备状态', label: '设备状态' },
        ]}
      />
      <InstrumentImportDrawer
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onSuccess={handleImportSuccess}
      />
    </>
  )
}