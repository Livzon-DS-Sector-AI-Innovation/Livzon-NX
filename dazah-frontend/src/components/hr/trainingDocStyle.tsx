'use client'

/**
 * 培训资料 5 个页签共用的"Word 文档保真"样式。
 *
 * 目标：文档渲染区（A4 内容）视觉与 SMP-HR-002-14 Word 模板一致——
 * 中文宋体、西文/数字 Times New Roman、5号(10.5pt)、Word 单倍行距、
 * 纯黑实线边框、页码 P{x}/{n} 与文档编号条。
 *
 * 仅作用于文档区（.doc-area 及其子元素），不影响导出/保存等操作按钮与表单控件。
 * 各组件在文档区外层加 <TrainingDocStyle /> 即可复用，避免重复定义。
 */
export default function TrainingDocStyle() {
  return (
    <style jsx global>{`
      /* ── 文档区基础字体（Word 保真） ─ */
      .doc-area, .doc-area * {
        font-family: 'Times New Roman', '宋体', SimSun, serif !important;
      }
      .doc-area {
        font-size: 10.5pt; /* 5号 */
        line-height: 1.4;
        color: #000;
        background: #fff;
      }

      /* ── 文档标题 ── */
      .doc-area .doc-title {
        font-size: 16pt;
        font-weight: 700;
        letter-spacing: 4px;
        text-align: center;
        margin: 4px 0 14px;
        position: relative;
        padding-bottom: 10px;
      }
      .doc-area .doc-title::after {
        content: '';
        position: absolute;
        left: 50%; bottom: 0;
        transform: translateX(-50%);
        width: 60px; height: 2px;
        background: linear-gradient(90deg, transparent, #1677ff, transparent);
        opacity: .7;
      }

      /* ── 页码 / 文档编号条 ── */
      .doc-area .doc-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 9pt;
        color: #000;
        margin-bottom: 4px;
      }
      .doc-area .doc-bar .doc-no {
        letter-spacing: 1px;
      }

      /* ── A4 纸面美化（屏幕显示，不影响打印） ── */
      .doc-area.a4-page, .doc-area .a4-page {
        position: relative;
        border-radius: 6px 6px 8px 8px;
        background: #fff;
        box-shadow:
          0 1px 2px rgba(15, 23, 42, 0.05),
          0 12px 32px rgba(15, 23, 42, 0.10),
          0 4px 10px rgba(15, 23, 42, 0.06);
        border: 1px solid #e2e8f0;
        overflow: hidden;
      }
      .doc-area.a4-page::before, .doc-area .a4-page::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: linear-gradient(90deg, #1677ff, #0958d9 45%, #1677ff);
      }
      .doc-area.a4-page { padding: 22px 26px 26px; }
      .doc-area .a4-page { padding: 22px 26px 26px; }

      /* ── 操作按钮美化（工具栏） ── */
      .doc-toolbar, .doc-toolbar .ant-space-item { display: inline-flex; align-items: center; }
      .doc-toolbar .ant-btn {
        border-radius: 8px;
        font-weight: 500;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.06);
        transition: all .18s ease;
      }
      .doc-toolbar .ant-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(16, 24, 40, 0.12); }
      .doc-toolbar .ant-btn-primary {
        background: linear-gradient(135deg, #1677ff, #0958d9);
        border-color: transparent;
      }

      /* ── 保真表格（纯黑实线边框） ── */
      .doc-area table.doc-table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        font-size: 10.5pt;
        border: 1.5px solid #000;
        background: #fff;
      }
      .doc-area .doc-table td {
        border: 1px solid #000;
        vertical-align: middle;
        padding: 5px 8px;
      }
      .doc-area .doc-table .doc-lbl {
        font-weight: 700;
        text-align: center;
        white-space: nowrap;
        background: #fff;
        font-size: 10.5pt;
      }
      .doc-area .doc-table .doc-head td {
        background: #fff;
        font-weight: 700;
        text-align: center;
        letter-spacing: 1px;
        border-top: 1.5px solid #000;
        border-bottom: 1.5px solid #000;
      }
      .doc-area .doc-table .doc-idx {
        text-align: center;
        font-variant-numeric: tabular-nums;
      }

      /* ── 文档模式下 antd 控件样式：填空用下划线 ── */
      .doc-area .ant-input,
      .doc-area .ant-input-affix-wrapper,
      .doc-area .ant-picker,
      .doc-area .ant-select .ant-select-selector,
      .doc-area .ant-input-number,
      .doc-area .ant-input-number-input,
      .doc-area textarea.ant-input {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
        border-radius: 0 !important;
        padding: 2px 4px !important;
        font-size: 10.5pt !important;
      }
      .doc-area .ant-input:not(textarea),
      .doc-area .ant-picker-input > input,
      .doc-area .ant-input-number-input,
      .doc-area .ant-select-selector {
        border-bottom: 1.5px solid #000 !important;
      }
      .doc-area .ant-input::placeholder,
      .doc-area .ant-picker-input > input::placeholder {
        color: #999 !important;
      }

      /* 打印保真 */
      @media print {
        .doc-area { font-size: 10.5pt; }
        .doc-area table.doc-table { border: 1px solid #000 !important; }
        .doc-area .doc-table td { border: 1px solid #000 !important; }
      }
    `}</style>
  )
}