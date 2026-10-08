'use server'

import * as change from './quality-change'
import * as capa from './quality-capa'
import * as deviation from './quality-deviation'
import * as legacy from './quality'
import { serverActionResult } from '@/lib/server-action-result'

export async function previewChangeImport(...args: Parameters<typeof change.previewChangeImport>) {
  return serverActionResult('quality.change.previewImport', () => change.previewChangeImport(...args))
}
export async function confirmChangeImport(...args: Parameters<typeof change.confirmChangeImport>) {
  return serverActionResult('quality.change.confirmImport', () => change.confirmChangeImport(...args))
}
export async function previewCapaImport(...args: Parameters<typeof capa.previewCapaImport>) {
  return serverActionResult('quality.capa.previewImport', () => capa.previewCapaImport(...args))
}
export async function confirmCapaImport(...args: Parameters<typeof capa.confirmCapaImport>) {
  return serverActionResult('quality.capa.confirmImport', () => capa.confirmCapaImport(...args))
}
export async function previewDeviationImport(...args: Parameters<typeof deviation.previewDeviationImport>) {
  return serverActionResult('quality.deviation.previewImport', () => deviation.previewDeviationImport(...args))
}
export async function confirmDeviationImport(...args: Parameters<typeof deviation.confirmDeviationImport>) {
  return serverActionResult('quality.deviation.confirmImport', () => deviation.confirmDeviationImport(...args))
}
export async function previewLegacyChangeImport(...args: Parameters<typeof legacy.previewChangeImport>) {
  return serverActionResult('quality.change.previewImport', () => legacy.previewChangeImport(...args))
}
export async function confirmLegacyChangeImport(...args: Parameters<typeof legacy.confirmChangeImport>) {
  return serverActionResult('quality.change.confirmImport', () => legacy.confirmChangeImport(...args))
}
export async function previewLegacyCapaImport(...args: Parameters<typeof legacy.previewCapaImport>) {
  return serverActionResult('quality.capa.previewImport', () => legacy.previewCapaImport(...args))
}
export async function confirmLegacyCapaImport(...args: Parameters<typeof legacy.confirmCapaImport>) {
  return serverActionResult('quality.capa.confirmImport', () => legacy.confirmCapaImport(...args))
}
export async function previewLegacyDeviationImport(...args: Parameters<typeof legacy.previewDeviationImport>) {
  return serverActionResult('quality.deviation.previewImport', () => legacy.previewDeviationImport(...args))
}
export async function confirmLegacyDeviationImport(...args: Parameters<typeof legacy.confirmDeviationImport>) {
  return serverActionResult('quality.deviation.confirmImport', () => legacy.confirmDeviationImport(...args))
}
