import {
  getBatchProgress,
  getProcessCatalog,
  getProcessExecutionRecords,
} from '@/actions/production'
import { Workshop203Client } from '@/components/production'
import type { components } from '@/types/generated/schema'

export const dynamic = 'force-dynamic'

type BatchProgress = components['schemas']['BatchProgressResponse']
type ProcessRecord = components['schemas']['ProcessExecutionRecordResponse']
type ProcessDefinition = components['schemas']['ProcessDefinition']

const emptyProgress: BatchProgress = {
  batches: [],
  steps: [],
  summary: {
    total_batches: 0,
    in_progress: 0,
    completed: 0,
    today_pack_count: 0,
    monthly_output_kg: 0,
    bottlenecks: [],
  },
}

export default async function Workshop203Page() {
  let initialProgress = emptyProgress
  let initialRecords: ProcessRecord[] = []
  let processCatalog: ProcessDefinition[] = []

  try {
    const response = await getBatchProgress('203')
    if (response.code === 200 && response.data) initialProgress = response.data
  } catch {
    initialProgress = emptyProgress
  }

  try {
    const response = await getProcessCatalog()
    if (response.code === 200 && response.data) processCatalog = response.data
  } catch {
    processCatalog = []
  }

  try {
    const response = await getProcessExecutionRecords({
      workshop_code: '203',
      page_size: 200,
    })
    if (response.code === 200 && response.data) initialRecords = response.data
  } catch {
    initialRecords = []
  }

  return (
    <div className="p-6">
      <Workshop203Client
        initialProgress={initialProgress}
        initialRecords={initialRecords}
        processCatalog={processCatalog}
      />
    </div>
  )
}
