'use server'

import { revalidatePath } from 'next/cache'
import {
  createOptimization,
  updateOptimization,
  deleteOptimization,
} from '@/lib/api/rd'
import type { OptimizationCreate, OptimizationUpdate } from '@/types/rd'

export async function createOptimizationAction(data: OptimizationCreate) {
  try {
    const optimization = await createOptimization(data)
    revalidatePath('/rd/process-optimization')
    return { success: true, data: optimization }
  } catch (error) {
    return { success: false, error: (error as Error).message }
  }
}

export async function updateOptimizationAction(id: string, data: OptimizationUpdate) {
  try {
    const optimization = await updateOptimization(id, data)
    revalidatePath('/rd/process-optimization')
    return { success: true, data: optimization }
  } catch (error) {
    return { success: false, error: (error as Error).message }
  }
}

export async function deleteOptimizationAction(id: string) {
  try {
    await deleteOptimization(id)
    revalidatePath('/rd/process-optimization')
    return { success: true }
  } catch (error) {
    return { success: false, error: (error as Error).message }
  }
}
