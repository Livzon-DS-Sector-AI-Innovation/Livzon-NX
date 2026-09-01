// mammoth 浏览器专用 bundle（主入口 lib/index.js 为 Node API，浏览器打包会卡死）
declare module 'mammoth/mammoth.browser.js' {
  interface ConvertResult {
    value: string
    messages: unknown[]
  }
  interface ConvertInput {
    arrayBuffer: ArrayBuffer
  }
  const mammoth: {
    convertToHtml(input: ConvertInput): Promise<ConvertResult>
  }
  export = mammoth
}