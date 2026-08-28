'use client'

import { pullOotLedgerRecords, createOotLedgerRecord, updateOotLedgerRecord, deleteOotLedgerRecord } from '@/actions/quality'
import { fetchOotLedgerRecords } from '@/lib/api/client/quality'
import { OosOotLedgerPageBase } from './OosOotLedgerPageBase'

export default function OotLedgerPage() {
  return (
    <OosOotLedgerPageBase
      config={{
        label: 'OOT',
        queryKeyPrefix: 'quality-oot',
        exportUrl: '/api/v1/quality/oos-oot/oot-ledger/export',
        fetchRecords: fetchOotLedgerRecords,
        pullRecords: pullOotLedgerRecords,
        createRecord: createOotLedgerRecord,
        updateRecord: updateOotLedgerRecord,
        deleteRecord: deleteOotLedgerRecord,
      }}
    />
  )
}
