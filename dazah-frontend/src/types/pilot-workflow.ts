// 中试研究类型定义

export type PilotWorkflowStatus = 'pending' | 'running' | 'waiting_approval' | 'completed' | 'failed'
export type PilotWorkflowStepStatus = 'pending' | 'running' | 'waiting_approval' | 'completed' | 'failed' | 'skipped'

export interface PilotWorkflowStep {
  id: string
  workflow_id: string
  step_order: number
  step_code: string
  step_name: string
  status: PilotWorkflowStepStatus
  input_data: Record<string, unknown> | null
  output_data: Record<string, unknown> | null
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export interface PilotWorkflow {
  id: string
  project_id: string | null
  product_name: string
  scale_up_ratio: number
  equipment_type: string
  equipment_volume: number
  input_document_path: string | null
  input_context: Record<string, unknown> | null
  status: PilotWorkflowStatus
  final_report: Record<string, unknown> | null
  created_at: string
  updated_at: string
  created_by: string | null
  updated_by: string | null
  steps: PilotWorkflowStep[]
}

export interface PilotWorkflowListItem {
  id: string
  product_name: string
  scale_up_ratio: number
  equipment_type: string
  equipment_volume: number
  status: PilotWorkflowStatus
  created_at: string
  step_count: number
  completed_step_count: number
}

export interface PilotWorkflowCreate {
  project_id?: string
  product_name: string
  scale_up_ratio: number
  equipment_type: string
  equipment_volume: number
  input_context?: Record<string, unknown>
}

export interface PilotWorkflowFilters {
  status?: PilotWorkflowStatus | ''
  keyword?: string
  page?: number
  page_size?: number
}

export interface PilotWorkflowListResponse {
  items: PilotWorkflowListItem[]
  total: number
  page: number
  page_size: number
}
