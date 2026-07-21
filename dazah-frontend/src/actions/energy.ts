'use server'

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import {
  previewEnergyMapping as previewEnergyMappingApi,
  saveEnergyFeishuConfig as saveEnergyFeishuConfigApi,
  saveEnergyMapping as saveEnergyMappingApi,
  testEnergyFeishuConfig as testEnergyFeishuConfigApi,
  triggerEnergySync as triggerEnergySyncApi,
  type EnergyFeishuConfigInput,
  type EnergyMappingInput,
  type EnergySyncTrigger,
  createEnergyFeishuSourceRoot as createEnergyFeishuSourceRootApi,
  deleteEnergyFeishuSourceRoot as deleteEnergyFeishuSourceRootApi,
  type EnergyFeishuSourceRootInput,
} from '@/lib/api/energy'

export async function saveEnergyFeishuConfig(payload: EnergyFeishuConfigInput) {
  const result = await saveEnergyFeishuConfigApi(payload, await getAuthHeaders())
  revalidatePath('/energy')
  revalidatePath('/energy/sources')
  return result
}

export async function createEnergyFeishuSourceRoot(payload: EnergyFeishuSourceRootInput) {
  const result = await createEnergyFeishuSourceRootApi(payload, await getAuthHeaders())
  revalidatePath('/energy/sources')
  return result
}

export async function deleteEnergyFeishuSourceRoot(rootId: string) {
  await deleteEnergyFeishuSourceRootApi(rootId, await getAuthHeaders())
  revalidatePath('/energy/sources')
}

export async function testEnergyFeishuConfig() {
  return testEnergyFeishuConfigApi(await getAuthHeaders())
}

export async function triggerEnergySync(payload: EnergySyncTrigger = { force: false }) {
  const result = await triggerEnergySyncApi(payload, await getAuthHeaders())
  revalidatePath('/energy')
  revalidatePath('/energy/sources')
  revalidatePath('/energy/data')
  revalidatePath('/energy/sync-runs')
  return result
}

export async function previewEnergyMapping(sheetId: string, payload: EnergyMappingInput) {
  return previewEnergyMappingApi(sheetId, payload, await getAuthHeaders())
}

export async function saveEnergyMapping(sheetId: string, payload: EnergyMappingInput) {
  const result = await saveEnergyMappingApi(sheetId, payload, await getAuthHeaders())
  revalidatePath('/energy')
  revalidatePath('/energy/sources')
  revalidatePath(`/energy/sources/${sheetId}`)
  return result
}
