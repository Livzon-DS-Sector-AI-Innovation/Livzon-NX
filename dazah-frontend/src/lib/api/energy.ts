import { serverApiUrl } from '@/lib/server-api'
import type { components, operations } from '@/types/generated/schema'

type Schema = components['schemas']

export type EnergyFeishuConfig = Schema['EnergyFeishuConfigResponse']
export type EnergyFeishuConfigInput = Schema['EnergyFeishuConfigUpsert']
export type EnergyConnectivity = Schema['EnergyFeishuConnectivityResult']
export type EnergySyncRun = Schema['EnergySyncRunResponse']
export type EnergySyncTrigger = Schema['EnergySyncTriggerRequest']
export type EnergySourceDocument = Schema['EnergySourceDocumentResponse']
export type EnergySourceSheet = Schema['EnergySourceSheetResponse']
export type EnergySnapshot = Schema['EnergySnapshotResponse']
export type EnergySnapshotRow = Schema['EnergySnapshotRowResponse']
export type EnergyMapping = Schema['EnergySheetMappingResponse']
export type EnergyMappingInput = Schema['EnergySheetMappingUpsert']
export type EnergyMappingPreview = Schema['EnergyMappingPreviewResponse']
export type EnergyOverview = Schema['EnergyOverviewResponse']
export type EnergyFeishuSourceRoot = Schema['EnergyFeishuSourceRootResponse']
export type EnergyFeishuSourceRootInput = Schema['EnergyFeishuSourceRootInput']

type ConfigEnvelope = Schema['EnergyApiResponse_EnergyFeishuConfigResponse_']
type ConnectivityEnvelope = Schema['EnergyApiResponse_EnergyFeishuConnectivityResult_']
type SyncRunEnvelope = Schema['EnergyApiResponse_EnergySyncRunResponse_']
type SyncRunsEnvelope = Schema['EnergyApiResponse_list_EnergySyncRunResponse__']
type DocumentsEnvelope = Schema['EnergyApiResponse_list_EnergySourceDocumentResponse__']
type SourcesEnvelope = Schema['EnergyApiResponse_list_EnergySourceSheetResponse__']
type SnapshotsEnvelope = Schema['EnergyApiResponse_list_EnergySnapshotResponse__']
type MappingEnvelope = Schema['EnergyApiResponse_Union_EnergySheetMappingResponse__NoneType__']
type MappingSaveEnvelope = Schema['EnergyApiResponse_EnergySheetMappingResponse_']
type MappingPreviewEnvelope = Schema['EnergyApiResponse_EnergyMappingPreviewResponse_']
type SnapshotRowsEnvelope = Schema['EnergyApiResponse_EnergySnapshotRowsData_']
type OverviewEnvelope = Schema['EnergyApiResponse_EnergyOverviewResponse_']

type SyncRunsQuery = NonNullable<
  operations['list_sync_runs_api_v1_energy_sync_runs_get']['parameters']['query']
>
type SourcesQuery = NonNullable<
  operations['list_source_sheets_api_v1_energy_sources_get']['parameters']['query']
>
type OverviewQuery = operations['get_overview_api_v1_energy_overview_get']['parameters']['query']
type ServerAuthHeaders = Record<string, string>

async function request<T>(
  url: string,
  options?: RequestInit,
  serverAuthHeaders?: ServerAuthHeaders,
): Promise<T> {
  const fullUrl = typeof window === 'undefined' ? serverApiUrl(url) : url
  const response = await fetch(fullUrl, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...serverAuthHeaders,
      ...options?.headers,
    },
  })
  const body = await response.json()
  if (!response.ok) {
    throw new Error(body.message || `请求失败: ${response.status}`)
  }
  return body as T
}

function queryString(params: Record<string, string | number | boolean | null | undefined>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  })
  const value = query.toString()
  return value ? `?${value}` : ''
}

export async function fetchEnergyFeishuConfig(): Promise<EnergyFeishuConfig> {
  return (await request<ConfigEnvelope>('/api/v1/energy/feishu-config')).data
}

export async function fetchEnergyFeishuSourceRoots(): Promise<EnergyFeishuSourceRoot[]> {
  return (
    await request<{ data: EnergyFeishuSourceRoot[] }>('/api/v1/energy/feishu/roots')
  ).data
}

export async function createEnergyFeishuSourceRoot(
  payload: EnergyFeishuSourceRootInput,
  serverAuthHeaders?: ServerAuthHeaders,
): Promise<EnergyFeishuSourceRoot> {
  return (
    await request<{ data: EnergyFeishuSourceRoot }>(
      '/api/v1/energy/feishu/roots',
      { method: 'POST', body: JSON.stringify(payload) },
      serverAuthHeaders,
    )
  ).data
}

export async function deleteEnergyFeishuSourceRoot(
  rootId: string,
  serverAuthHeaders?: ServerAuthHeaders,
): Promise<void> {
  await request(
    `/api/v1/energy/feishu/roots/${rootId}`,
    { method: 'DELETE' },
    serverAuthHeaders,
  )
}

export async function saveEnergyFeishuConfig(
  payload: EnergyFeishuConfigInput,
  serverAuthHeaders?: ServerAuthHeaders,
): Promise<EnergyFeishuConfig> {
  return (
    await request<ConfigEnvelope>('/api/v1/energy/feishu-config', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }, serverAuthHeaders)
  ).data
}

export async function testEnergyFeishuConfig(
  serverAuthHeaders?: ServerAuthHeaders,
): Promise<EnergyConnectivity> {
  return (
    await request<ConnectivityEnvelope>('/api/v1/energy/feishu-config/test', {
      method: 'POST',
    }, serverAuthHeaders)
  ).data
}

export async function triggerEnergySync(
  payload: EnergySyncTrigger,
  serverAuthHeaders?: ServerAuthHeaders,
): Promise<EnergySyncRun> {
  return (
    await request<SyncRunEnvelope>('/api/v1/energy/sync-runs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }, serverAuthHeaders)
  ).data
}

export async function fetchEnergySyncRuns(
  params: SyncRunsQuery = {},
): Promise<SyncRunsEnvelope> {
  return request<SyncRunsEnvelope>(`/api/v1/energy/sync-runs${queryString(params)}`)
}

export async function fetchEnergyDocuments(periodMonth?: string): Promise<EnergySourceDocument[]> {
  return (
    await request<DocumentsEnvelope>(
      `/api/v1/energy/sources/documents${queryString({ period_month: periodMonth })}`,
    )
  ).data
}

export async function fetchEnergySources(params: SourcesQuery = {}): Promise<EnergySourceSheet[]> {
  return (await request<SourcesEnvelope>(`/api/v1/energy/sources${queryString(params)}`)).data
}

export async function fetchEnergySnapshots(sheetId: string): Promise<EnergySnapshot[]> {
  return (
    await request<SnapshotsEnvelope>(`/api/v1/energy/sources/${sheetId}/snapshots`)
  ).data
}

export async function fetchEnergyMapping(sheetId: string): Promise<EnergyMapping | null> {
  return (
    await request<MappingEnvelope>(`/api/v1/energy/sources/${sheetId}/mapping`)
  ).data
}

export async function previewEnergyMapping(
  sheetId: string,
  payload: EnergyMappingInput,
  serverAuthHeaders?: ServerAuthHeaders,
): Promise<EnergyMappingPreview> {
  return (
    await request<MappingPreviewEnvelope>(
      `/api/v1/energy/sources/${sheetId}/mapping/preview`,
      { method: 'POST', body: JSON.stringify(payload) },
      serverAuthHeaders,
    )
  ).data
}

export async function saveEnergyMapping(
  sheetId: string,
  payload: EnergyMappingInput,
  serverAuthHeaders?: ServerAuthHeaders,
): Promise<EnergyMapping> {
  return (
    await request<MappingSaveEnvelope>(`/api/v1/energy/sources/${sheetId}/mapping`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }, serverAuthHeaders)
  ).data
}

export async function fetchEnergySnapshotRows(
  snapshotId: string,
  params: { page?: number; page_size?: number } = {},
): Promise<SnapshotRowsEnvelope> {
  return request<SnapshotRowsEnvelope>(
    `/api/v1/energy/snapshots/${snapshotId}/rows${queryString(params)}`,
  )
}

export async function fetchEnergyOverview(params: OverviewQuery): Promise<EnergyOverview> {
  return (
    await request<OverviewEnvelope>(`/api/v1/energy/overview${queryString(params)}`)
  ).data
}
