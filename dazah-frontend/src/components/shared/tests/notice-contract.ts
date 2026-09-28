import { readdirSync, readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { expect, it } from 'vitest'

function sourceFiles(directory: string): string[] {
  if (!existsSync(directory)) return []
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name)
    return entry.isDirectory() ? sourceFiles(path) : /\.(ts|tsx)$/.test(path) && !/\.(test|spec)\./.test(path) ? [path] : []
  })
}

/** Enforce the design contract at every module boundary, including server pages. */
export function checkModuleNoticeContract(module: string) {
  it(`${module} routes all persistent notices through the platform component`, () => {
    const files = [
      ...sourceFiles(join(process.cwd(), 'src/components', module)),
      ...sourceFiles(join(process.cwd(), 'src/app/(dashboard)', module)),
    ]
    let noticeUsers = 0
    for (const file of files) {
      const source = readFileSync(file, 'utf8')
      const antImports = [...source.matchAll(/import\s*\{([^}]+)\}\s*from\s*['"]antd['"]/g)]
      expect(antImports.some((match) => /\bAlert\b/.test(match[1])), `${file}: use PlatformNotice`).toBe(false)
      expect(/role=["']alert["']/.test(source), `${file}: use PlatformNotice for custom alert boxes`).toBe(false)
      if (source.includes('@/components/shared/PlatformNotice')) noticeUsers += 1
    }
    expect(noticeUsers, `${module}: migrated notice integration must be present`).toBeGreaterThan(0)
  })
}
