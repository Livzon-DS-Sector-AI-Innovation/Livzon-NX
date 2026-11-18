const errorNames = /^(?:error|err|e|cause|failure|[a-z]+Error)$/i
const feedbackFields = new Set(['content', 'message', 'description', 'title', 'subTitle'])

const userFeedback = {
  meta: {
    type: 'problem',
    schema: [],
    messages: { raw: '使用 getUserErrorMessage 或结构化的 Server Action 结果展示错误。' },
  },
  create(context) {
    const { visitorKeys } = context.sourceCode
    function containsRawError(node) {
      if (!node || /^(CallExpression|ArrowFunctionExpression|ObjectExpression|JSXElement)$/.test(node.type)) return false
      if (node.type === 'MemberExpression') {
        return node.property.name === 'message' && node.object.type === 'Identifier' && errorNames.test(node.object.name)
      }
      return (visitorKeys[node.type] ?? []).some(key => {
        const child = node[key]
        return Array.isArray(child) ? child.some(containsRawError) : containsRawError(child)
      })
    }
    function check(node) {
      if (containsRawError(node)) context.report({ node, messageId: 'raw' })
    }
    return {
      CallExpression({ callee, arguments: [arg] }) {
        if (!arg) return
        if (callee.type === 'Identifier' && /^set.*Error(?:Msg|Message|Text)?$/.test(callee.name)) check(arg)
        if (callee.type !== 'MemberExpression' || !/^(error|warning)$/.test(callee.property.name)) return
        const receiver = callee.object.name
        if (!/^(message|notification|modal|Modal)$/.test(receiver)) return
        if (arg.type !== 'ObjectExpression') {
          if (receiver === 'message') check(arg)
          return
        }
        for (const prop of arg.properties) {
          if (prop.type === 'Property' && feedbackFields.has(prop.key.name)) check(prop.value)
        }
      },
      JSXAttribute(node) {
        if (/^(Alert|PlatformNotice|Result)$/.test(node.parent.name.name) && feedbackFields.has(node.name.name)) {
          check(node.value?.expression)
        }
      },
    }
  },
}

export default userFeedback
