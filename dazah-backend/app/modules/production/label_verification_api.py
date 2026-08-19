from datetime import date
from uuid import UUID

from fastapi import Depends, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.label_verification_schemas import (
    LabelVerificationCreate,
    LabelVerificationUpdate,
)
from app.modules.production.label_verification_service import LabelVerificationService
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE
from app.shared.schemas import PageParams

router = create_module_router(MODULES_BY_CODE["quality"])


def get_label_verification_service(
    session: AsyncSession = Depends(get_db),
) -> LabelVerificationService:
    return LabelVerificationService(session)


# ─── LabelVerification Routes ───


@router.get("/label-verifications", summary="标签复核记录列表")
async def list_label_verifications(
    batch_number: str | None = Query(None, description="批号搜索"),
    product_name: str | None = Query(None, description="产品名称搜索"),
    result_status: str | None = Query(None, description="结论状态筛选"),
    start_date: date | None = Query(None, description="复核日期起始"),
    end_date: date | None = Query(None, description="复核日期截止"),
    page_params: PageParams = Depends(),
    service: LabelVerificationService = Depends(get_label_verification_service),
):
    verifications, total = await service.list_verifications(
        batch_number=batch_number,
        product_name=product_name,
        result_status=result_status,
        start_date=start_date,
        end_date=end_date,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    data = [v.model_dump(mode="json") for v in verifications]
    return paginated_response(
        data=data,
        page=page_params.page,
        page_size=page_params.page_size,
        total=total,
    )


@router.post("/label-verifications", summary="创建标签复核记录")
async def create_label_verification(
    payload: LabelVerificationCreate,
    service: LabelVerificationService = Depends(get_label_verification_service),
):
    verification = await service.create_verification(payload)
    return success_response(
        data=verification.model_dump(mode="json"),
        message="标签复核记录创建成功",
        status_code=201,
    )


@router.get("/label-verifications/statistics", summary="标签复核统计")
async def get_label_verification_statistics(
    service: LabelVerificationService = Depends(get_label_verification_service),
):
    stats = await service.get_statistics()
    return success_response(data=stats.model_dump(mode="json"))


@router.get(
    "/label-verifications/batch/{batch_number}",
    summary="按批号查询历史记录",
)
async def get_verifications_by_batch(
    batch_number: str,
    service: LabelVerificationService = Depends(get_label_verification_service),
):
    verifications = await service.get_by_batch_number(batch_number)
    data = [v.model_dump(mode="json") for v in verifications]
    return success_response(data=data)


@router.get(
    "/label-verifications/{verification_id}",
    summary="标签复核记录详情",
)
async def get_label_verification(
    verification_id: UUID,
    service: LabelVerificationService = Depends(get_label_verification_service),
):
    verification = await service.get_verification(verification_id)
    return success_response(
        data=verification.model_dump(mode="json"),
    )


@router.put(
    "/label-verifications/{verification_id}",
    summary="更新标签复核记录",
)
async def update_label_verification(
    verification_id: UUID,
    payload: LabelVerificationUpdate,
    service: LabelVerificationService = Depends(get_label_verification_service),
):
    verification = await service.update_verification(verification_id, payload)
    return success_response(
        data=verification.model_dump(mode="json"),
        message="标签复核记录更新成功",
    )


@router.delete(
    "/label-verifications/{verification_id}",
    summary="删除标签复核记录",
)
async def delete_label_verification(
    verification_id: UUID,
    service: LabelVerificationService = Depends(get_label_verification_service),
):
    await service.delete_verification(verification_id)
    return success_response(message="标签复核记录删除成功")


@router.post(
    "/label-verifications/upload-video",
    summary="上传标签复核视频",
)
async def upload_label_verification_video(
    file: UploadFile,
    service: LabelVerificationService = Depends(get_label_verification_service),
):
    """上传视频文件，返回文件 key 和文件名"""
    import os
    from fastapi import UploadFile
    from datetime import datetime
    from app.core.config import get_settings

    settings = get_settings()
    upload_dir = os.path.join(settings.UPLOAD_DIR, "label-verification")
    os.makedirs(upload_dir, exist_ok=True)

    file_ext = os.path.splitext(file.filename or ".mp4")[1]
    timestamp = int(datetime.now().timestamp())
    safe_name = f"video_{timestamp}_{file.filename or 'unknown'}"
    file_path = os.path.join(upload_dir, safe_name)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    file_key = f"label-verification/{safe_name}"
    return success_response(
        data={
            "file_key": file_key,
            "file_name": file.filename or safe_name,
            "file_size": len(content),
        },
        message="视频上传成功",
    )


@router.post(
    "/label-verifications/analyze-video",
    summary="分析标签复核视频",
)
async def analyze_label_verification_video(
    file_key: str,
    fps: float = 1.0,
    service: LabelVerificationService = Depends(get_label_verification_service),
):
    """分析视频中的标签信息，返回 AI 识别结果"""
    import os
    from app.core.config import get_settings
    from app.modules.production.label_verification_video_service import LabelVerificationVideoService
    from app.core.llm import llm_client, LLMOutputError

    settings = get_settings()
    video_path = os.path.join(settings.UPLOAD_DIR, file_key)

    if not os.path.exists(video_path):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="视频文件不存在")

    # 提取视频帧
    video_service = LabelVerificationVideoService(settings.UPLOAD_DIR)
    frames = video_service.extract_frames(video_path, fps=fps, max_frames=20)

    if not frames:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="无法从视频中提取帧")

    # 使用统一的 LLM 客户端（视觉模型）

    # 构建提示词
    prompt = """请仔细分析这张图片中的标签信息，提取以下内容并以 JSON 格式返回：
{
  "batch_number": "批号",
  "product_name": "产品名称",
  "production_date": "生产日期 (YYYY-MM-DD)",
  "expiry_date": "有效期至 (YYYY-MM-DD)",
  "total_barrels": 总桶数 (数字),
  "standard_barrels": 整桶数 (数字),
  "remainder_barrel": 零头桶数 (0或1),
  "standard_weight": 整桶重量 (数字，单位kg),
  "remainder_weight": 零头重量 (数字，单位kg),
  "total_weight": 总重量 (数字，单位kg),
  "confidence": 识别置信度 (0-100),
  "notes": "备注说明"
}

如果某些信息无法识别，请将其设为 null。请确保返回有效的 JSON。"""

    # 使用第一帧和最后一帧进行分析
    images_to_analyze = [frames[0]]
    if len(frames) > 1:
        images_to_analyze.append(frames[-1])

    result = await llm_client.chat_vision(prompt, images_to_analyze)

    # 解析 JSON 结果
    import json
    try:
        # 清理可能的 markdown 格式
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        ai_result = json.loads(cleaned)
    except json.JSONDecodeError:
        ai_result = {"raw_response": result, "error": "JSON 解析失败"}

        return {
            "code": 200,
            "message": "视频分析完成",
            "data": {
                "frames_extracted": len(frames),
                "fps_used": fps,
                "ai_result": ai_result,
            },
        }

    except Exception as e:
        logger.error(f"视频分析失败: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"视频分析失败: {str(e)}")


# ─── 自动对比接口 ───


from pydantic import BaseModel, Field


class AutoCompareRequest(BaseModel):
    """自动对比请求体"""
    video_file_key: str = Field(..., description="视频文件 key")
    batch_number: str = Field(..., description="批号")
    product_name: str = Field("", description="产品名称")
    production_date: str = Field("", description="生产日期")
    expiry_date: str = Field("", description="有效期至")
    total_barrels: int | None = Field(None, description="总桶数")
    standard_barrels: int | None = Field(None, description="整桶数")
    remainder_barrel: int | None = Field(None, description="零头桶数")
    standard_weight: float | None = Field(None, description="整桶重量")
    remainder_weight: float | None = Field(None, description="零头重量")
    total_weight: float | None = Field(None, description="总重量")


@router.post(
    "/label-verifications/auto-compare",
    summary="自动对比视频与表单数据",
)
async def auto_compare_video(
    payload: AutoCompareRequest,
    service: LabelVerificationService = Depends(get_label_verification_service),
):
    """
    自动分析视频中的标签信息，与表单数据逐项对比，返回 8 项核对结论。
    如果识别不全，会自动降低帧率重新分析。
    """
    import os
    from app.core.config import get_settings
    from app.modules.production.label_verification_video_service import (
        LabelVerificationVideoService,
    )
    from app.core.llm import llm_client

    settings = get_settings()

    # 拼接视频路径
    video_path = os.path.join(settings.UPLOAD_DIR, payload.video_file_key)
    if not os.path.exists(video_path):
        # 尝试 label-verification 子目录
        video_path = os.path.join(
            settings.UPLOAD_DIR, "label-verification",
            os.path.basename(payload.video_file_key)
        )
        if not os.path.exists(video_path):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="视频文件不存在")

    # 构建表单数据
    form_data = {
        "batch_number": payload.batch_number,
        "product_name": payload.product_name,
        "production_date": payload.production_date,
        "expiry_date": payload.expiry_date,
        "total_barrels": payload.total_barrels,
        "standard_barrels": payload.standard_barrels,
        "remainder_barrel": payload.remainder_barrel,
        "standard_weight": payload.standard_weight,
        "remainder_weight": payload.remainder_weight,
        "total_weight": payload.total_weight,
    }

    # 初始化 AI 服务（使用视觉模型）
    ai_api_key = os.getenv("AI_API_KEY", "")
    ai_base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
    ai_vision_model = os.getenv("AI_VISION_MODEL", "gpt-4o")

    # 使用统一的 LLM 客户端（视觉模型）

    # 执行自动对比
    video_service = LabelVerificationVideoService(settings.UPLOAD_DIR)

    try:
        result = await video_service.analyze_and_compare(
            video_path=video_path,
            form_data=form_data,
            ai_service=ai_service,
    )
    except Exception as e:
        logger.error(f"自动对比失败: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"视频分析失败: {str(e)}")

    return success_response(
        data=result,
        message="自动对比完成",
    )
