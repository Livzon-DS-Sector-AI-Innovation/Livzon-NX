// 全局测试环境补齐（React 19 + happy-dom）
// 1) React 19 的 act() 要求测试环境声明 IS_REACT_ACT_ENVIRONMENT=true（官方要求）。
// 2) happy-dom v20 在 Node 25 / vitest 4 下 window.localStorage 方法缺失
//    （getItem/clear 等为 undefined），统一补内存实现，仅在方法缺失时生效，
//    不影响其它环境。

export {}

declare global {
  // React 19 测试环境的 act 支持标志（happy-dom / vitest 未声明）
  var IS_REACT_ACT_ENVIRONMENT: boolean | undefined
}

globalThis.IS_REACT_ACT_ENVIRONMENT = true

if (
  typeof window !== 'undefined' &&
  window.localStorage &&
  typeof window.localStorage.clear !== 'function'
) {
  const store = new Map<string, string>()
  const storage: Storage = {
    get length() {
      return store.size
    },
    clear: () => store.clear(),
    getItem: (key: string) => {
      const value = store.get(key)
      return value === undefined ? null : value
    },
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    removeItem: (key: string) => {
      store.delete(key)
    },
    setItem: (key: string, value: string) => {
      store.set(key, String(value))
    },
  }
  Object.defineProperty(window, 'localStorage', { value: storage, configurable: true })
}
