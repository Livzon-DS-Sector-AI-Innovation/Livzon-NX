/**
 * 培训模块部门解析规则（与后端 training_dept_resolver.py 一致，配置表驱动）：
 * 映射配置统一从 /api/v1/hr/training/dept-mappings 获取（HR 设置"培训部门映射"维护），
 * 前端不再维护硬编码字典。
 *
 * 解析顺序：二级部门命中映射(second/both) → 一级部门命中映射(first/both)
 *  → 一级部门在培训部门列表中存在 → 回退二级部门。
 *
 * 未加载完成时各函数直通返回（不阻塞 UI），映射就绪后通过 useDeptMappings()
 * 订阅版本号触发重渲染。
 */
import { useSyncExternalStore } from 'react'
import { fetchTrainingDeptMappings, type DeptMappingItem } from '@/lib/api/client/hr'

// ── 模块级缓存 + 订阅 ──

let mappingCache: DeptMappingItem[] | null = null
let mappingPromise: Promise<DeptMappingItem[]> | null = null
let version = 0
const listeners = new Set<() => void>()

function notify() {
  version += 1
  listeners.forEach((l) => l())
}

function subscribeDeptMappings(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function getDeptMappingsVersion(): number {
  return version
}

/** 拉取映射配置（幂等：进程内只拉一次；失败可重试） */
export function ensureDeptMappings(): Promise<DeptMappingItem[]> {
  if (mappingCache) return Promise.resolve(mappingCache)
  if (!mappingPromise) {
    mappingPromise = fetchTrainingDeptMappings()
      .then((data) => {
        mappingCache = data
        mappingPromise = null  // 先清 promise，再 notify，避免竞态
        notify()
        return data
      })
      .catch((err) => {
        mappingPromise = null  // 失败时也清空，允许重试
        throw err
      })
  }
  return mappingPromise
}

/** React Hook：订阅映射配置版本（配置加载/变更后触发重渲染） */
export function useDeptMappings(): { loaded: boolean; version: number } {
  const v = useSyncExternalStore(subscribeDeptMappings, getDeptMappingsVersion, getDeptMappingsVersion)
  return { loaded: mappingCache !== null, version: v }
}

/** 强制重新拉取映射配置（HR 设置页增删改后调用，全局解析规则即时生效） */
export async function refreshDeptMappings(): Promise<DeptMappingItem[]> {
  mappingCache = null
  mappingPromise = null
  const data = await fetchTrainingDeptMappings()
  mappingCache = data
  notify()
  return data
}

// ── 解析函数（签名保持不变；未加载时直通返回） ──

const RESOLVE_TYPES = new Set(['special', 'alias'])

function resolveIndex(): Map<string, DeptMappingItem[]> {
  const bySource = new Map<string, DeptMappingItem[]>()
  for (const m of mappingCache ?? []) {
    if (!RESOLVE_TYPES.has(m.mapping_type)) continue
    const arr = bySource.get(m.source_name) ?? []
    arr.push(m)
    bySource.set(m.source_name, arr)
  }
  for (const arr of bySource.values()) arr.sort((a, b) => a.priority - b.priority)
  return bySource
}

/** 员工档案部门 → 培训部门名（与后端 resolve_training_department 一致） */
export function resolveTrainingDept(
  department: string | null | undefined,
  subDepartment: string | null | undefined,
  trainingDepts: string[],
): string {
  const bySource = resolveIndex()
  // 1. 二级部门优先（201 家族 both 条目优先命中）
  if (subDepartment) {
    const hit = (bySource.get(subDepartment) || []).find(
      (m) => m.match_level === 'second' || m.match_level === 'both',
    )
    if (hit?.target_name) return hit.target_name
  }
  // 2. 一级部门命中映射
  if (department) {
    const hit = (bySource.get(department) || []).find(
      (m) => m.match_level === 'first' || m.match_level === 'both',
    )
    if (hit?.target_name) return hit.target_name
  }
  if (!department) return subDepartment || ''
  // 3. 一级部门在培训部门列表中存在 → 使用一级部门
  if (trainingDepts.includes(department)) return department
  // 4. 回退二级部门
  return subDepartment || department
}

/** 打印统一显示名（print_unify 映射，如 201二车间（MC）→201二车间、102二车间（DR）→102二车间） */
export function unifyDept(dept: string | undefined | null): string {
  if (!dept) return ''
  const hit = (mappingCache ?? []).find(
    (m) => m.mapping_type === 'print_unify' && m.source_name === dept,
  )
  return hit?.target_name ?? dept
}

/** 兼容旧名：201 二车间 打印统一显示（内部走通用 unifyDept） */
export function unify201Dept(dept: string | undefined | null): string {
  return unifyDept(dept)
}

/** 输入侧部门选项：去掉 exclude 名、补 force_show 名（原 with201SubDepts 通用版） */
export function withSubDepts(list: string[]): string[] {
  const exclude = new Set(
    (mappingCache ?? []).filter((m) => m.mapping_type === 'exclude').map((m) => m.source_name),
  )
  const force = (mappingCache ?? [])
    .filter((m) => m.mapping_type === 'force_show')
    .map((m) => m.source_name)
  const s = new Set(list.filter((d) => !exclude.has(d)))
  force.forEach((d) => s.add(d))
  return [...s].sort((a, b) => a.localeCompare(b, 'zh'))
}

/** 兼容旧名：201 二车间 输入选项处理（内部走通用 withSubDepts） */
export function with201SubDepts(list: string[]): string[] {
  return withSubDepts(list)
}

// 201 二车间 常量（页面仍引用，保持导出）
export const DEPT_201 = '201二车间'
export const DEPT_201_MC = '201二车间（MC）'
export const DEPT_201_DR = '201二车间（DR）'

/** 候选人来源（人员配置弹窗/飞书导入：目标培训部门行 ← 飞书源部门） */
export function getCandidateSourceMap(): Record<string, string> {
  const map: Record<string, string> = {}
  for (const m of mappingCache ?? []) {
    if (m.mapping_type === 'candidate_source' && m.target_name) {
      map[m.source_name] = m.target_name
    }
  }
  return map
}

/** 人员配置弹窗专属规则（drop 不参与 / extra 额外行 / no_expand 不展开） */
export function getModalRules(): {
  drop: Set<string>
  extra: string[]
  noExpand: Set<string>
} {
  const drop = new Set<string>()
  const extra: string[] = []
  const noExpand = new Set<string>()
  for (const m of mappingCache ?? []) {
    if (m.mapping_type === 'modal_drop') drop.add(m.source_name)
    else if (m.mapping_type === 'modal_extra') extra.push(m.source_name)
    else if (m.mapping_type === 'modal_no_expand') noExpand.add(m.source_name)
  }
  return { drop, extra: extra.sort((a, b) => a.localeCompare(b, 'zh')), noExpand }
}
