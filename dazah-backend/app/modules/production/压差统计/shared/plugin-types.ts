// ---- plugin:differential_pressure_inspection_image_ocr_1 ----
// ============================================================
// 插件 differential_pressure_inspection_image_ocr_1 (压差巡检图片OCR识别) 的类型定义
// 由 get_plugin_ai_json 自动生成
// ============================================================

export interface DifferentialPressureInspectionImageOcrOneInput {
  /** 待识别的压差巡检图片 */
  inspection_image: string[];
  /** 额外的提取要求（可选） */
  additional_extraction_requirements?: string;
}

/**
 * capabilityClient.load('differential_pressure_inspection_image_ocr_1').call<DifferentialPressureInspectionImageOcrOneOutput>('imageToJson', input)
 * 直接返回此类型，无 .data 包装，直接解构使用：
 * const { records } = result;
 */
export interface DifferentialPressureInspectionImageOcrOneOutput {
  /** 巡检记录数组，每一个元素对应表格中的一行数据 */
  records: unknown[];
}
// ---- end:differential_pressure_inspection_image_ocr_1 ----