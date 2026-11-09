// Generate the reviewed backend page-menu catalog from the existing static navigation.
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
const reviewedModules = new Set(['production', 'hr', 'warehouse', 'quality', 'procurement', 'equipment', 'energy'])
const output = moduleMenus.filter((menuModule) => reviewedModules.has(menuModule.moduleCode)).map(node)
// The merged ledger has one navigation entry but two independently granted
// pages. Export the input page too, so regenerating names cannot remove its ACL.
const energy = output.find(item => item.key === 'energy')
const ledger = moduleMenus.find(item => item.moduleCode === 'energy')?.children.find(item => item.key === 'reports')
if (energy && ledger?.activePaths?.includes('/energy/entry')) {
  const index = energy.children.findIndex(item => item.key === 'reports')
  energy.children.splice(index, 0, node({ key: 'entry', label: '原始数据填写', path: '/energy/entry' }))
}
const target = path.resolve(root, '../dazah-backend/app/platform/identity/page_menu_catalog.json')
// Reviewed permission pages can differ from navigation in other modules.
// Scope a name update so their catalog entries remain intact.
const moduleIndex = process.argv.indexOf('--module')
const selectedModule = moduleIndex < 0 ? undefined : process.argv[moduleIndex + 1]
if (moduleIndex >= 0 && !reviewedModules.has(selectedModule)) {
  throw new Error('Unknown reviewed module for --module')
}
let catalog = output
if (selectedModule) {
  const existing = JSON.parse(fs.readFileSync(target, 'utf8'))
  const updated = output.find(item => item.key === selectedModule)
  if (!existing.some(item => item.key === selectedModule)) throw new Error('Module missing from reviewed catalog')
  catalog = existing.map(item => item.key === selectedModule ? updated : item)
}
const content = `${JSON.stringify(catalog, null, 2)}\n`
if (process.argv.includes('--check')) {
  if (!fs.existsSync(target) || fs.readFileSync(target, 'utf8') !== content) {
    throw new Error('页面目录与前端静态菜单不一致，请运行 generate-page-menu.mjs')
  }
} else {
  fs.writeFileSync(target, content)
}
process.stdout.write(`Page menu catalog ${process.argv.includes('--check') ? 'verified' : 'generated'} (${output.length} modules)\n`)
