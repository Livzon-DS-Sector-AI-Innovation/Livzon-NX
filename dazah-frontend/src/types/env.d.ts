/**
 * Vitest 测试环境探测类型声明。
 * 组件在测试环境（happy-dom）下跳过 blob: iframe 渲染避免 ERR_INVALID_URL，
 * 通过 `import.meta.env?.MODE === 'test'` 判断——Next.js 不内置该类型，
 * 此处补齐，避免 tsc 报错。
 */
interface ImportMetaEnv {
  readonly MODE?: string
  readonly [key: string]: string | undefined
}

interface ImportMeta {
  readonly env?: ImportMetaEnv
}
