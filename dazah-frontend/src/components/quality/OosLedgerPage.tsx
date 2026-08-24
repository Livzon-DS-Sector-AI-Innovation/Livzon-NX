'use client'

import { pullOosLedgerRecords, createOosLedgerRecord, updateOosLedgerRecord, deleteOosLedgerRecord } from '@/actions/quality'
import { fetchOosLedgerRecords } from '@/lib/api/client/quality'
import { OosOotLedgerPageBase } from './OosOotLedgerPageBase'

export default function OosLedgerPage() {
  return (
    <OosOotLedgerPageBase
      config={{
        label: 'OOS',
        queryKeyPrefix: 'quality-oos',
        exportUrl: '/api/v1/quality/oos-oot/oos-ledger/export',
        fetchRecords: fetchOosLedgerRecords,
        pullRecords: pullOosLedgerRecords,
        createRecord: createOosLedgerRecord,
        updateRecord: updateOosLedgerRecord,
        deleteRecord: deleteOosLedgerRecord,
      }}
    />
  )
}
