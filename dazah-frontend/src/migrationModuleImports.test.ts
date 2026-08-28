import { describe, expect, it } from 'vitest'

type ModuleLoader = () => Promise<unknown>
type ImportMetaWithGlob = ImportMeta & {
  glob: <T>(patterns: string[], options: { eager: false }) => Record<string, T>
}

const moduleLoaders = (import.meta as ImportMetaWithGlob).glob<ModuleLoader>(
  [
    './components/quality/**/*.{ts,tsx}',
    './components/registration/**/*.{ts,tsx}',
    './components/hr/**/*.{ts,tsx}',
    './components/warehouse/**/*.{ts,tsx}',
    './components/system/**/*.{ts,tsx}',
    '!./components/**/*.test.{ts,tsx}',
  ],
  { eager: false },
)

describe('migrated module import contract', () => {
  it('loads every migrated component without a missing runtime dependency', async () => {
    const failures: string[] = []

    for (const [path, load] of Object.entries(moduleLoaders)) {
      try {
        await load()
      } catch (error) {
        failures.push(`${path}: ${error instanceof Error ? error.message : String(error)}`)
      }
    }

    expect(Object.keys(moduleLoaders).length).toBeGreaterThan(0)
    expect(failures).toEqual([])
  }, 60000)
})
