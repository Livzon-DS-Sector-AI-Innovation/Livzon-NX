import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'
import { expect, it } from 'vitest'

it('keeps energy interaction controls in Ant Design instead of native widgets or browser dialogs', () => {
  const directory = fileURLToPath(new URL('.', import.meta.url))
  const files = readdirSync(directory).filter(file => file.endsWith('.tsx') && !file.endsWith('.test.tsx'))
  const nativeControls = new Set(['input', 'select', 'textarea', 'button', 'table', 'dialog', 'details', 'summary', 'progress', 'meter'])
  const violations: string[] = []
  for (const file of files) {
    const source = ts.createSourceFile(file, readFileSync(`${directory}/${file}`, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    function visit(node: ts.Node) {
      if ((ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) && nativeControls.has(node.tagName.getText(source))) {
        violations.push(`${file}: native ${node.tagName.getText(source)}`)
      }
      if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression) && node.expression.expression.getText(source) === 'window' && ['alert', 'confirm', 'prompt'].includes(node.expression.name.text)) {
        violations.push(`${file}: browser ${node.expression.name.text}`)
      }
      ts.forEachChild(node, visit)
    }
    visit(source)
  }
  expect(files.length).toBeGreaterThan(10)
  expect(violations).toEqual([])
})
