import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { moduleMenus, type SubMenuItem } from './menu-config'

const dashboardRoot = resolve(process.cwd(), 'src/app/(dashboard)')
const appRoot = resolve(process.cwd(), 'src/app')
const openapi = JSON.parse(
  readFileSync(resolve(process.cwd(), 'src/types/generated/openapi.json'), 'utf8'),
) as { paths: Record<string, Record<string, unknown>> }

function collectMenuPaths(items: SubMenuItem[], output: string[]): void {
  for (const item of items) {
    if (item.path) output.push(item.path)
    if (item.children) collectMenuPaths(item.children, output)
  }
}

function resolvePage(pathname: string): string | null {
  const routePath = pathname.split('?', 1)[0]
  if (routePath === '#' || routePath.startsWith('/admin/')) return null
  let current = dashboardRoot
  for (const segment of routePath.split('/').filter(Boolean)) {
    const direct = join(current, segment)
    if (existsSync(direct)) {
      current = direct
      continue
    }
    const dynamic = readdirSync(current, { withFileTypes: true }).find(
      (entry) => entry.isDirectory() && /^\[.+\]$/.test(entry.name),
    )
    if (!dynamic) return null
    current = join(current, dynamic.name)
  }
  const page = join(current, 'page.tsx')
  return existsSync(page) ? page : null
}

function hasOperation(pathname: string, method: string): boolean {
  return Boolean(openapi.paths[pathname]?.[method.toLowerCase()])
}

function collectSourceFiles(root: string): string[] {
  const stack = [root]
  const files: string[] = []
  while (stack.length) {
    const current = stack.pop()!
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const fullPath = join(current, entry.name)
      if (entry.isDirectory()) stack.push(fullPath)
      else if (/\.(ts|tsx)$/.test(entry.name) && !/\.test\.(ts|tsx)$/.test(entry.name)) {
        files.push(fullPath)
      }
    }
  }
  return files
}

function normalizeFrontendPath(pathname: string): string {
  const normalized = pathname
    .replace(/\$\{[^}]+\}/g, '{param}')
    .split('?', 1)[0]
    .replace(/\{param\}$/, '')
    .replace(/\/+$/, '')
  return normalized.includes('${')
    ? normalized.slice(0, normalized.indexOf('${')).replace(/\/+$/, '')
    : normalized
}

function matchesOpenApiPath(pathname: string, apiPath: string): boolean {
  const actualSegments = pathname.split('/').filter(Boolean)
  const apiSegments = apiPath.replace(/\/+$/, '').split('/').filter(Boolean)
  return (
    actualSegments.length === apiSegments.length &&
    actualSegments.every(
      (segment, index) =>
        segment.includes('{param}') ||
        apiSegments[index].includes('{') ||
        segment === apiSegments[index],
    )
  )
}

describe('five-module migration contract', () => {
  it('resolves every non-empty module menu path to a Next page', () => {
    const paths: string[] = []
    const migratedModuleCodes = new Set(['quality', 'registration', 'hr', 'warehouse'])
    for (const menu of moduleMenus) {
      if (migratedModuleCodes.has(menu.moduleCode)) collectMenuPaths(menu.children, paths)
    }

    const uniquePaths = [...new Set(paths)]
    const missing = uniquePaths
      .filter((pathname) => !pathname.startsWith('/admin/'))
      .filter((pathname) => pathname !== '#')
      .filter((pathname) => !resolvePage(pathname))
    expect(missing).toEqual([])
    expect(uniquePaths).not.toContain('/hr/attendance')
    expect(uniquePaths.length).toBeGreaterThan(100)
  })

  it('keeps the three quality inspection landing pages usable', () => {
    for (const section of ['items', 'instruments', 'finished']) {
      const page = resolve(dashboardRoot, 'quality/inspection', section, 'page.tsx')
      expect(readFileSync(page, 'utf8')).toContain('InspectionSectionLanding')
    }
  })

  it('keeps repaired compatibility operations in generated OpenAPI', () => {
    const required: Array<[string, string]> = [
      ['/api/v1/hr/candidates/{candidate_id}/send-notice', 'post'],
      ['/api/v1/hr/offboarding-records/{record_id}/certificate', 'post'],
      ['/api/v1/quality/capas/{capa_id}/add-execution-track', 'post'],
      ['/api/v1/quality/capas/{capa_id}/delete-execution-track', 'post'],
      ['/api/v1/quality/capas/{capa_id}/submit-evaluation', 'post'],
      ['/api/v1/registration/authorization-letters/{letter_id}/download', 'get'],
      ['/api/v1/registration/reference-standards/{record_id}/download', 'get'],
      ['/api/v1/registration/supplementary-replies/{reply_id}/download', 'get'],
      ['/api/v1/warehouse/feishu-config/test', 'post'],
      ['/api/v1/warehouse/feishu/roots/{root_id}/discover', 'post'],
      ['/api/v1/warehouse/page-data/{page_key}', 'put'],
      ['/api/v1/warehouse/analytics/query', 'post'],
      ['/api/v1/identity/admin/menus', 'get'],
    ]

    for (const [pathname, method] of required) {
      expect(hasOperation(pathname, method), `${method} ${pathname}`).toBe(true)
    }
  })

  it('resolves literal migrated frontend API paths in generated OpenAPI', () => {
    const sourceRoots = [
      resolve(process.cwd(), 'src/actions'),
      resolve(process.cwd(), 'src/lib/api'),
      resolve(process.cwd(), 'src/components'),
      resolve(process.cwd(), 'src/app/(dashboard)/quality'),
      resolve(process.cwd(), 'src/app/(dashboard)/registration'),
      resolve(process.cwd(), 'src/app/(dashboard)/hr'),
      resolve(process.cwd(), 'src/app/(dashboard)/warehouse'),
      resolve(process.cwd(), 'src/app/(dashboard)/system'),
    ]
    const endpointPattern = /[`'"]((?:\/api\/v1\/(?:quality|registration|hr|warehouse|identity))[^`'"\r\n]*)[`'"]/g
    const references = new Map<string, string[]>()
    for (const root of sourceRoots) {
      for (const file of collectSourceFiles(root)) {
        const source = readFileSync(file, 'utf8')
        for (const match of source.matchAll(endpointPattern)) {
          if (match[1].includes('${')) continue
          const pathname = normalizeFrontendPath(match[1])
          if (!pathname || pathname.split('/').length < 5) continue
          if (pathname.endsWith('/validation-audit')) continue
          const current = references.get(pathname) ?? []
          current.push(file)
          references.set(pathname, current)
        }
      }
    }

    const paths = Object.keys(openapi.paths)
    const missing = [...references.entries()]
      .filter(([pathname]) => !paths.some((apiPath) => matchesOpenApiPath(pathname, apiPath)))
      .map(([pathname, files]) => `${pathname}: ${files.join(', ')}`)
    expect(missing).toEqual([])
  })

  it('does not retain known dead download-url or placeholder references', () => {
    const sourceRoot = resolve(process.cwd(), 'src')
    const sourceFiles = collectSourceFiles(sourceRoot)
    const deadReferences = sourceFiles
      .filter((file) => !file.endsWith('migrationContract.test.ts'))
      .filter((file) => {
        const source = readFileSync(file, 'utf8')
        return source.includes('/download-url')
      })
    expect(deadReferences).toEqual([])

    const placeholderPages = sourceFiles
      .filter((file) => file.startsWith(appRoot))
      .filter((file) => readFileSync(file, 'utf8').includes('ModulePlaceholder'))
    expect(placeholderPages).toEqual([])
  })
})
