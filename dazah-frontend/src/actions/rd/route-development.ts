'use server'

import { revalidatePath } from 'next/cache'
import {
  createRoute,
  updateRoute,
  deleteRoute,
} from '@/lib/api/rd'
import type { RouteCreate, RouteUpdate } from '@/types/rd'

export async function createRouteAction(data: RouteCreate) {
  try {
    const route = await createRoute(data)
    revalidatePath('/rd/route-development')
    return { success: true, data: route }
  } catch (error) {
    return { success: false, error: (error as Error).message }
  }
}

export async function updateRouteAction(routeId: string, data: RouteUpdate) {
  try {
    const route = await updateRoute(routeId, data)
    revalidatePath('/rd/route-development')
    revalidatePath(`/rd/route-development/${routeId}`)
    return { success: true, data: route }
  } catch (error) {
    return { success: false, error: (error as Error).message }
  }
}

export async function deleteRouteAction(routeId: string) {
  try {
    await deleteRoute(routeId)
    revalidatePath('/rd/route-development')
    return { success: true }
  } catch (error) {
    return { success: false, error: (error as Error).message }
  }
}
