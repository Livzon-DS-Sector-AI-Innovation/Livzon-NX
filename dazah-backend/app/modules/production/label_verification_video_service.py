"""Video analysis service for label verification — auto-compare logic."""

import base64
import json
import logging
import os
import re
from datetime import date, datetime

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class LabelVerificationVideoService:
    """视频分析服务 - 提取帧并调用 AI 视觉模型识别标签信息，自动与表单对比"""

    def __init__(self, upload_dir: str = "./uploads"):
        self.upload_dir = upload_dir

    # ─── 帧提取 ───

    def extract_frames(
        self,
        video_path: str,
        fps: float = 1.0,
        max_frames: int = 30,
    ) -> list[str]:
        """从视频中提取帧，返回 base64 编码的图片列表"""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"无法打开视频文件: {video_path}")

        video_fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / video_fps if video_fps > 0 else 0

        logger.info(
            f"视频信息: {video_path}, FPS={video_fps:.2f}, "
            f"总帧数={total_frames}, 时长={duration:.1f}秒"
        )

        frame_interval = max(1, int(video_fps / fps))
        frames_base64 = []
        current_frame = 0

        while cap.isOpened() and len(frames_base64) < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            if current_frame % frame_interval == 0:
                _, buffer = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75]
                )
                img_base64 = base64.b64encode(buffer).decode("utf-8")
                frames_base64.append(f"data:image/jpeg;base64,{img_base64}")

            current_frame += 1

        cap.release()
        logger.info(f"提取了 {len(frames_base64)} 帧 (目标 FPS={fps})")
        return frames_base64

    def get_video_info(self, video_path: str) -> dict:
        """获取视频基本信息"""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"无法打开视频文件: {video_path}")

        info = {
            "fps": cap.get(cv2.CAP_PROP_FPS),
            "total_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "duration": 0,
        }
        info["duration"] = info["total_frames"] / info["fps"] if info["fps"] > 0 else 0
        cap.release()
        return info

    # ─── AI 识别 ───

    def _build_recognition_prompt(self) -> str:
        """构建 AI 视觉识别的提示词"""
        return """你是一个药品生产标签核验专家。请仔细分析这些视频帧截图，识别标签上的所有信息。

这些帧来自同一段视频，展示的是同一批产品的标签和桶。请综合所有帧的信息，尽量完整地识别以下内容。

请以 JSON 格式返回识别结果：
{
  "batch_number": "批号（如 QS32603006）",
  "product_name": "产品名称",
  "production_date": "生产日期，格式 YYYY-MM-DD",
  "expiry_date": "有效期至，格式 YYYY-MM-DD",
  "total_barrels": "总桶数（数字，如果无法确定填 null）",
  "standard_barrels": "整桶数（数字，如果无法确定填 null）",
  "remainder_barrel": "是否有零头桶（0 或 1，无法确定填 null）",
  "remainder_barrel_number": "零头桶的桶号（字符串，如 '第5桶'，无零头填 null）",
  "standard_weight": "整桶重量合计（数字 kg，无法确定填 null）",
  "remainder_weight": "零头重量（数字 kg，无法确定填 null）",
  "total_weight": "总重量（数字 kg，无法确定填 null）",
  "barrels_seen": "识别到的桶号列表（如 ['1', '2', '3']，无法识别填 []）",
  "confidence": "整体识别置信度（0-100）",
  "notes": "识别过程中的备注，如哪些信息不清晰、哪些帧有遮挡等"
}

注意事项：
1. 批号通常以 QS 开头加数字
2. 日期格式可能是 YYYY-MM-DD、YYYY年MM月DD日 等，请统一转为 YYYY-MM-DD
3. 重量单位可能是 kg，请注意换算
4. 如果某个信息在多帧中都能看到，以清晰度最高的那帧为准
5. 如果某些信息完全无法识别，请设为 null，不要猜测
6. barrels_seen 列出你在视频中实际看到的所有桶的编号"""

    def _build_detailed_prompt(self, form_data: dict) -> str:
        """构建带表单数据的详细对比提示词"""
        return f"""你是一个药品生产标签核验专家。请仔细分析这些视频帧截图，将标签上的信息与以下表单数据进行逐项对比。

表单数据：
- 批号：{form_data.get('batch_number', '未填写')}
- 产品名称：{form_data.get('product_name', '未填写')}
- 生产日期：{form_data.get('production_date', '未填写')}
- 有效期至：{form_data.get('expiry_date', '未填写')}
- 总桶数：{form_data.get('total_barrels', '未填写')}
- 整桶数：{form_data.get('standard_barrels', '未填写')}
- 零头桶数：{form_data.get('remainder_barrel', '未填写')}
- 整桶重量：{form_data.get('standard_weight', '未填写')} kg
- 零头重量：{form_data.get('remainder_weight', '未填写')} kg
- 总重量：{form_data.get('total_weight', '未填写')} kg

请对以下 8 项逐一判断（true=一致，false=不一致或无法确认）：

1. check_batch_number: 视频中标签上的批号是否与表单批号一致
2. check_production_date: 视频中每桶的生产日期是否与表单一致
3. check_expiry_date: 视频中每桶的有效期至是否与表单一致
4. check_standard_barrels: 视频中整桶的数量、桶号、重量是否与表单一致
5. check_remainder_barrel: 视频中零头的数量、桶号、重量是否与表单一致
6. check_total_weight: 视频中的总重量是否与表单一致（允许 ±0.5kg 误差）
7. check_all_barrels_identified: 视频中是否能看到表单中列出的每一桶
8. check_exception_handled: 如果以上 7 项全部为 true，则此项为 true；否则为 false

同时请返回从视频中识别到的实际数据，方便人工复核。

请以 JSON 格式返回：
{{
  "check_batch_number": true/false,
  "check_production_date": true/false,
  "check_expiry_date": true/false,
  "check_standard_barrels": true/false,
  "check_remainder_barrel": true/false,
  "check_total_weight": true/false,
  "check_all_barrels_identified": true/false,
  "check_exception_handled": true/false,
  "ai_batch_number": "AI识别到的批号",
  "ai_product_name": "AI识别到的产品名称",
  "ai_production_date": "AI识别到的生产日期",
  "ai_expiry_date": "AI识别到的有效期至",
  "ai_total_barrels": "AI识别到的总桶数（数字或null）",
  "ai_standard_barrels": "AI识别到的整桶数（数字或null）",
  "ai_remainder_barrel": "AI识别到的零头桶数（数字或null）",
  "ai_standard_weight": "AI识别到的整桶重量（数字或null）",
  "ai_remainder_weight": "AI识别到的零头重量（数字或null）",
  "ai_total_weight": "AI识别到的总重量（数字或null）",
  "ai_barrels_seen": ["识别到的桶号列表"],
  "confidence": 整体置信度(0-100),
  "detail_reasons": {{
    "check_batch_number": "判断理由",
    "check_production_date": "判断理由",
    "check_expiry_date": "判断理由",
    "check_standard_barrels": "判断理由",
    "check_remainder_barrel": "判断理由",
    "check_total_weight": "判断理由",
    "check_all_barrels_identified": "判断理由"
  }},
  "notes": "其他备注"
}}"""

    def _parse_ai_response(self, raw: str) -> dict:
        """解析 AI 返回的 JSON，处理 markdown 格式等"""
        cleaned = raw.strip()
        # 去掉 markdown 代码块
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            start_idx = 0
            for i, line in enumerate(lines):
                if not line.strip().startswith("```"):
                    start_idx = i
                    break
            cleaned = "\n".join(lines[start_idx:])
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        return json.loads(cleaned)

    def _is_recognition_complete(self, result: dict) -> bool:
        """判断识别结果是否完整（关键信息是否都有）"""
        critical_fields = [
            "batch_number",
            "production_date",
            "expiry_date",
        ]
        for field in critical_fields:
            if result.get(field) is None:
                return False

        # 置信度低于 60 也算不完整
        confidence = result.get("confidence", 0)
        if isinstance(confidence, (int, float)) and confidence < 60:
            return False

        return True

    def _is_comparison_complete(self, result: dict) -> bool:
        """判断对比结果是否完整（8项是否都有明确判断）"""
        check_fields = [
            "check_batch_number",
            "check_production_date",
            "check_expiry_date",
            "check_standard_barrels",
            "check_remainder_barrel",
            "check_total_weight",
            "check_all_barrels_identified",
        ]
        for field in check_fields:
            val = result.get(field)
            if val is None:
                return False

        confidence = result.get("confidence", 0)
        if isinstance(confidence, (int, float)) and confidence < 50:
            return False

        return True

    async def analyze_and_compare(
        self,
        video_path: str,
        form_data: dict,
        ai_service,
        initial_fps: float = 1.0,
        max_retry_fps: float = 0.3,
    ) -> dict:
        """
        核心方法：分析视频并与表单数据自动对比。
        如果识别不全，自动降低帧率重试。

        返回结构:
        {
            "checks": { 8 项对比结果 },
            "ai_data": { AI 识别到的数据 },
            "confidence": 置信度,
            "frames_count": 提取帧数,
            "fps_used": 实际使用的帧率,
            "retry_count": 重试次数,
            "reasons": { 各项判断理由 },
        }
        """
        retry_count = 0
        current_fps = initial_fps

        while current_fps >= max_retry_fps:
            logger.info(
                f"视频分析第 {retry_count + 1} 轮, FPS={current_fps}"
            )

            # 提取帧
            frames = self.extract_frames(
                video_path, fps=current_fps, max_frames=25
            )
            if not frames:
                raise ValueError("无法从视频中提取到任何帧")

            # 选择关键帧：第一帧、中间帧、最后帧，尽量覆盖不同内容
            selected_frames = self._select_key_frames(frames, max_count=12)

            # 调用 AI 进行对比分析
            prompt = self._build_detailed_prompt(form_data)

            try:
                raw_response = await ai_service.chat_vision(
                    prompt, selected_frames
                )
                result = self._parse_ai_response(raw_response)
            except Exception as e:
                logger.warning(f"AI 分析失败 (FPS={current_fps}): {e}")
                result = {"error": str(e), "confidence": 0}

            # 判断是否需要降帧率重试
            if self._is_comparison_complete(result):
                logger.info(
                    f"分析完成, 置信度={result.get('confidence')}, "
                    f"帧数={len(selected_frames)}, FPS={current_fps}"
                )
                return self._format_comparison_result(
                    result, len(selected_frames), current_fps, retry_count
                )

            # 识别不完整，降低帧率重试
            retry_count += 1
            current_fps = max(current_fps * 0.5, max_retry_fps)
            if current_fps < max_retry_fps:
                break

            logger.info(
                f"识别不完整 (置信度={result.get('confidence')}), "
                f"降低帧率到 {current_fps} 重试"
            )

        # 最终结果（即使不完整也返回）
        return self._format_comparison_result(
            result, len(selected_frames), current_fps, retry_count
        )

    def _select_key_frames(
        self, frames: list[str], max_count: int = 12
    ) -> list[str]:
        """从所有帧中选择关键帧，尽量均匀分布"""
        if len(frames) <= max_count:
            return frames

        # 均匀采样
        step = len(frames) / max_count
        selected = []
        for i in range(max_count):
            idx = int(i * step)
            if idx < len(frames):
                selected.append(frames[idx])

        return selected

    def _format_comparison_result(
        self,
        result: dict,
        frames_count: int,
        fps_used: float,
        retry_count: int,
    ) -> dict:
        """格式化对比结果"""
        check_fields = [
            "check_batch_number",
            "check_production_date",
            "check_expiry_date",
            "check_standard_barrels",
            "check_remainder_barrel",
            "check_total_weight",
            "check_all_barrels_identified",
        ]

        checks = {}
        for field in check_fields:
            checks[field] = bool(result.get(field, False))

        # 异常处理：前 7 项全部通过才为 True
        all_pass = all(checks.values())
        checks["check_exception_handled"] = all_pass

        # AI 识别到的数据
        ai_data = {
            "batch_number": result.get("ai_batch_number"),
            "product_name": result.get("ai_product_name"),
            "production_date": result.get("ai_production_date"),
            "expiry_date": result.get("ai_expiry_date"),
            "total_barrels": result.get("ai_total_barrels"),
            "standard_barrels": result.get("ai_standard_barrels"),
            "remainder_barrel": result.get("ai_remainder_barrel"),
            "standard_weight": result.get("ai_standard_weight"),
            "remainder_weight": result.get("ai_remainder_weight"),
            "total_weight": result.get("ai_total_weight"),
            "barrels_seen": result.get("ai_barrels_seen", []),
        }

        # 计算总体结论
        if all_pass:
            result_status = "全部一致"
            result_summary = "✅✅✅ 全部一致"
        else:
            failed = [
                k for k, v in checks.items() if not v
            ]
            result_status = "存在差异"
            result_summary = f"❌ {len(failed)} 项不一致"

        return {
            "checks": checks,
            "ai_data": ai_data,
            "confidence": result.get("confidence", 0),
            "frames_count": frames_count,
            "fps_used": fps_used,
            "retry_count": retry_count,
            "reasons": result.get("detail_reasons", {}),
            "notes": result.get("notes", ""),
            "result_status": result_status,
            "result_summary": result_summary,
        }
