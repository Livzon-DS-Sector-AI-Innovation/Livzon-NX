// Generate the first-batch backend menu seed from the existing static navigation.
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const cache = new Map()
function load(source) {
  const filename = path.resolve(source)
  if (cache.has(filename)) return cache.get(filename)
  const loadedModule = { exports: {} }
  cache.set(filename, loadedModule.exports)
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
  vm.runInNewContext(code, { module: loadedModule, exports: loadedModule.exports, require: (specifier) => {
    if (!specifier.startsWith('.')) throw new Error(`Static menu has external dependency: ${specifier}`)
    return load(path.resolve(path.dirname(filename), `${specifier}.ts`))
  } }, { filename })
  return loadedModule.exports
}
function node(item) {
  return { key: item.key, name: item.label, path: item.path || '',
    icon: item.icon || null, permission_code: item.permission || null,
    disabled: Boolean(item.disabled), children: item.children?.map(node) || null }
}
const { moduleMenus } = load(path.join(root, 'src/lib/menu-config.ts'))
const firstBatch = new Set(['hr', 'warehouse', 'quality', 'procurement'])
const output = moduleMenus.filter((menuModule) => firstBatch.has(menuModule.moduleCode)).map(node)
const target = path.resolve(root, '../dazah-backend/app/platform/identity/page_menu_catalog.json')
const content = `${JSON.stringify(output, null, 2)}\n`
if (process.argv.includes('--check')) {
  if (!fs.existsSync(target) || fs.readFileSync(target, 'utf8') !== content) {
    throw new Error('页面目录与前端静态菜单不一致，请运行 generate-page-menu.mjs')
  }
} else {
  fs.writeFileSync(target, content)
}
process.stdout.write(`Page menu catalog ${process.argv.includes('--check') ? 'verified' : 'generated'} (${output.length} modules)\n`)
