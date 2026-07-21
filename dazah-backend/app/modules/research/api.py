"""研发项目 API 路由."""

import uuid
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import paginated_response, success_response
from app.modules.research import service
from app.modules.research.schemas import (
    ResearchProjectCreate,
    ResearchProjectResponse,
    ResearchProjectUpdate,
)
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["research"])


@router.post("/projects", summary="创建研发项目")
async def create_project(
    data: ResearchProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    project = await service.create_project(db, data)
    return success_response(data=ResearchProjectResponse.model_validate(project))


@router.get("/projects", summary="获取研发项目列表")
async def get_projects(
    stage: str | None = Query(None, description="项目阶段"),
    status: str | None = Query(None, description="项目状态"),
    keyword: str | None = Query(None, description="搜索项目编号或名称"),
    project_type: str | None = Query(None, description="项目类型过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    projects, total = await service.get_projects(
        db, stage=stage, status=status, keyword=keyword, project_type=project_type,
        page=page, page_size=page_size
    )
    return paginated_response(
        data=[ResearchProjectResponse.model_validate(p) for p in projects],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/projects/{project_id}", summary="获取研发项目详情")
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    project = await service.get_project(db, project_id)
    return success_response(data=ResearchProjectResponse.model_validate(project))


@router.put("/projects/{project_id}", summary="更新研发项目")
async def update_project(
    project_id: uuid.UUID,
    data: ResearchProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    project = await service.update_project(db, project_id, data)
    return success_response(data=ResearchProjectResponse.model_validate(project))


@router.delete("/projects/{project_id}", summary="删除研发项目")
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    await service.delete_project(db, project_id)
    return success_response(data={"message": "项目已删除"})


@router.post("/ich/q3c/analyze", summary="ICH Q3C 溶剂残留分析")
async def analyze_ich_q3c(
    file: UploadFile = File(...),
    route: str = Query("oral", description="给药途径"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    file_content = await file.read()
    filename = file.filename or "unknown"
    result = await service.analyze_ich_q3c(db, file_content, filename, route)
    return success_response(data=result)



@router.post("/ich/analyze", summary="ICH Q3C/Q3D 联合分析")
async def analyze_ich_combined(
    file: UploadFile = File(...),
    route: str = Query("oral", description="给药途径"),
    use_llm: bool = Query(False, description="是否使用 LLM 增强"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    file_content = await file.read()
    filename = file.filename or "unknown"
    result = await service.analyze_ich_combined(db, file_content, filename, route, use_llm)
    return success_response(data=result)


@router.get("/ich/records", summary="获取 ICH Q3C/Q3D 杂质识别记录列表")
async def get_ich_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    records, total = await service.get_ich_records(db, page=page, page_size=page_size)
    return paginated_response(
        data=[
            {
                "id": str(r.id),
                "filename": r.filename,
                "route": r.route,
                "q3c_result": r.q3c_result,
                "q3d_result": r.q3d_result,
                "llm_used": r.llm_used,
                "notes": r.notes,
                "created_at": r.created_at.isoformat(),
            }
            for r in records
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/ich/records/{record_id}", summary="获取 ICH Q3C/Q3D 杂质识别记录详情")
async def get_ich_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    record = await service.get_ich_record(db, record_id)
    return success_response(
        data={
            "id": str(record.id),
            "filename": record.filename,
            "route": record.route,
            "q3c_result": record.q3c_result,
            "q3d_result": record.q3d_result,
            "llm_used": record.llm_used,
            "notes": record.notes,
            "created_at": record.created_at.isoformat(),
        }
    )


@router.delete("/ich/records/{record_id}", summary="删除 ICH Q3C/Q3D 杂质识别记录")
async def delete_ich_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    await service.delete_ich_record(db, record_id)
    return success_response(data={"message": "记录已删除"})


@router.post("/edbo/optimize", summary="EDBO+ 贝叶斯优化")
async def edbo_optimize(
    file: UploadFile = File(..., description="反应范围 CSV 文件"),
    objectives: str = Body(..., description="目标列名，逗号分隔"),
    objective_modes: str = Body("max", description="目标方向，逗号分隔（max/min）"),
    batch_size: int = Body(5, ge=1, le=100, description="建议实验数量"),
    save_prediction: bool = Body(False, description="是否保存预测文件"),
    current_user: CurrentUser = None,
) -> JSONResponse:
    """
    使用 EDBO+ 进行贝叶斯反应优化。

    上传 CSV 文件（反应范围），指定目标列和优化方向，返回建议的实验列表。
    如果 save_prediction=True，还会返回预测文件（包含所有实验的模型预测结果）。
    """
    from app.modules.research.edbo_runner import run_edbo_optimization
    from app.modules.research.schemas import EDBOOptimizeResponse

    # Parse comma-separated strings
    obj_list = [o.strip() for o in objectives.split(",") if o.strip()]
    mode_list = [m.strip() for m in objective_modes.split(",") if m.strip()]

    if len(obj_list) != len(mode_list):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"objectives ({len(obj_list)}) and objective_modes ({len(mode_list)}) must have the same length"
        )

    # Read CSV content
    try:
        csv_content = (await file.read()).decode("utf-8")
    except UnicodeDecodeError:
        from app.core.response import error_response
        return error_response(message="文件编码错误：请使用 UTF-8 编码的 CSV 文件")

    # Run EDBO+ optimization
    try:
        result = await run_edbo_optimization(
            csv_content=csv_content,
            objectives=obj_list,
            objective_modes=mode_list,
            batch_size=batch_size,
            save_prediction=save_prediction,
        )
    except RuntimeError as e:
        from app.core.response import error_response
        return error_response(message=str(e))

    return success_response(data=EDBOOptimizeResponse(**result))


@router.post("/edbo/generate-scope", summary="生成反应范围")
async def edbo_generate_scope(
    components: dict = Body(..., description="组件定义，支持两种格式：1) 直接值列表 {name: [v1,v2,...]} 2) 范围定义 {name: {type: 'numeric', lower: x, upper: y, data_points: n}} 或 {name: {type: 'categorical', values: [...]}}"),
    objectives: list[str] = Body(default=[], description="优化目标名称列表，会作为新列添加到结果CSV中，初始值为PENDING"),
    batch_size: int = Body(default=5, ge=1, le=100, description="通量大小，表示同时进行的实验数量")
):
    """
    生成反应范围 CSV（所有组合的笛卡尔积）
    
    支持两种组件格式：
    
    1. 简单值列表（直接枚举）:
    ```json
    {
        "solvent": ["THF", "DMSO"],
        "catalyst": ["Pd", "Ni"]
    }
    ```
    
    2. 范围定义（数值型自动生成等间隔值）:
    ```json
    {
        "temperature": {"type": "numeric", "lower": 30, "upper": 90, "data_points": 4},
        "solvent": {"type": "categorical", "values": ["THF", "DMSO", "MeOH"]}
    }
    ```
    
    数值型组件会自动处理有效数字，避免浮点精度问题。
    """
    import itertools
    import math
    import pandas as pd
    from fastapi.responses import StreamingResponse
    import io
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"generate-scope called with objectives: {objectives}")
    logger.info(f"generate-scope components: {components}")
    logger.info(f"generate-scope batch_size: {batch_size}")
    
    def count_significant_digits(num):
        """Count the number of significant digits in a number."""
        if num == 0:
            return 1
        num_str = str(num).lower()
        if 'e' in num_str:
            mantissa = num_str.split('e')[0].replace('.', '').lstrip('0')
            return len(mantissa)
        if '.' in num_str:
            integer_part, decimal_part = num_str.split('.')
            integer_part = integer_part.lstrip('0')
            if integer_part:
                return len(integer_part) + len(decimal_part)
            else:
                decimal_part = decimal_part.lstrip('0')
                return len(decimal_part)
        else:
            return len(num_str.lstrip('0'))
    
    def round_to_significant_digits(num, sig_digits):
        """Round a number to the specified number of significant digits."""
        if num == 0:
            return 0
        if abs(num) == float('inf') or math.isnan(num):
            return num
        magnitude = 10 ** (sig_digits - 1 - int(math.floor(math.log10(abs(num)))))
        rounded = round(num * magnitude) / magnitude
        return rounded
    
    def generate_numeric_values(lower, upper, data_points):
        """Generate numeric values with proper significant digit handling."""
        if lower > upper:
            raise ValueError(f"下限 ({lower}) 不能大于上限 ({upper})")
        if data_points <= 1:
            raise ValueError(f"数据点数必须大于 1")
        
        values = []
        if data_points == 2:
            return [lower, upper]
        
        interval = (upper - lower) / (data_points - 1)
        
        # Check for extreme case: too many data points for small intervals
        if abs(lower) > 1e-15:
            relative_interval = interval / abs(lower)
            if relative_interval < 1e-6:
                raise ValueError(f"数据点过多，间隔过小")
        
        # Determine significant digits
        lower_sig_digits = count_significant_digits(lower)
        upper_sig_digits = count_significant_digits(upper)
        target_sig_digits = min(lower_sig_digits, upper_sig_digits)
        
        # Check if first in-between value rounds to lower limit
        first_in_between = lower + interval
        rounded_first = round_to_significant_digits(first_in_between, target_sig_digits)
        if abs(rounded_first - lower) < 1e-10:
            # Increase significant digits until different
            current_sig_digits = target_sig_digits + 1
            while current_sig_digits <= 15:
                rounded_first = round_to_significant_digits(first_in_between, current_sig_digits)
                if abs(rounded_first - lower) > 1e-10:
                    target_sig_digits = current_sig_digits
                    break
                current_sig_digits += 1
        
        # Generate all values
        for i in range(data_points):
            exact_value = lower + i * interval
            if abs(exact_value) == float('inf') or math.isnan(exact_value):
                values.append(exact_value)
            else:
                rounded_value = round_to_significant_digits(exact_value, target_sig_digits)
                values.append(rounded_value)
        
        return values
    
    # Validate input
    if not components:
        raise HTTPException(status_code=400, detail="组件定义不能为空")
    
    # Process each component
    processed_components = {}
    for key, value in components.items():
        if isinstance(value, list):
            # Simple list format
            processed_components[key] = value
        elif isinstance(value, dict):
            # Range definition format
            comp_type = value.get('type', 'categorical')
            if comp_type == 'numeric':
                lower = value.get('lower')
                upper = value.get('upper')
                data_points = value.get('data_points')
                if lower is None or upper is None or data_points is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"组件 '{key}' 缺少必要参数 (lower, upper, data_points)"
                    )
                try:
                    processed_components[key] = generate_numeric_values(
                        float(lower), float(upper), int(data_points)
                    )
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=f"组件 '{key}': {str(e)}")
            elif comp_type == 'categorical':
                cat_values = value.get('values', [])
                if not cat_values:
                    raise HTTPException(
                        status_code=400,
                        detail=f"组件 '{key}' 的值列表不能为空"
                    )
                processed_components[key] = cat_values
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"组件 '{key}' 的类型无效: {comp_type}"
                )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"组件 '{key}' 的格式无效"
            )
    
    # Calculate total combinations
    n_combinations = 1
    for key, values in processed_components.items():
        n_combinations *= len(values)
    
    if n_combinations > 10000:
        raise HTTPException(
            status_code=400,
            detail=f"组合数量过大 ({n_combinations})，请减少组件选项"
        )
    
    # Generate Cartesian product
    keys = list(processed_components.keys())
    values = [processed_components[key] for key in keys]
    
    scope = [dict(zip(keys, combination)) for combination in itertools.product(*values)]
    df_scope = pd.DataFrame(scope)
    
    # Convert to CSV (without objective columns - EDBO+ will add them)
    csv_buffer = io.StringIO()
    df_scope.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)
    scope_csv = csv_buffer.getvalue()
    
    # If objectives are defined, run EDBO+ to get initial sampling recommendations
    # IMPORTANT: Do NOT add objective columns with PENDING values before calling EDBO+.
    # EDBO+ detects missing objective columns and performs initial sampling automatically.
    # If we add PENDING columns first, EDBO+ thinks the scope already exists and refuses to run.
    logger.info(f"Checking objectives: {objectives}, length: {len(objectives)}")
    if objectives:
        logger.info(f"Objectives found, calling EDBO+ for initial sampling with: {objectives}")
        try:
            from app.modules.research.edbo_runner import run_edbo_optimization
            objective_modes = ['max'] * len(objectives)
            
            result = await run_edbo_optimization(
                csv_content=scope_csv,
                objectives=objectives,
                objective_modes=objective_modes,
                batch_size=batch_size,
                save_prediction=False,
            )
            
            result_csv = result.get("csv_data", scope_csv)
            return {
                "csv_data": result_csv,
                "row_count": len(scope),
                "columns": keys + objectives + ["priority"],
                "recommended_experiments": result_csv,
                "optimization_completed": True
            }
        except Exception as e:
            logger.error(f"EDBO+ optimization failed: {e}")
            # Add PENDING objective columns for the fallback response
            for obj in objectives:
                df_scope[obj] = "PENDING"
            csv_buffer = io.StringIO()
            df_scope.to_csv(csv_buffer, index=False)
            csv_buffer.seek(0)
            scope_csv_with_pending = csv_buffer.getvalue()
            
            return {
                "csv_data": scope_csv_with_pending,
                "row_count": len(scope),
                "columns": keys + objectives,
                "optimization_completed": False,
                "optimization_error": str(e)
            }
    
    return {
        "csv_data": scope_csv,
        "row_count": len(scope),
        "columns": keys,
        "optimization_completed": False
    }


# ===== Pilot Workflow API =====

import os
import uuid as uuid_module

from app.modules.research import repository as pilot_repo
from app.modules.research.pilot_workflow.engine import (
    start_workflow as start_workflow_engine,
    approve_step as approve_step_engine,
)
from app.modules.research.schemas import (
    PilotWorkflowCreate,
    PilotWorkflowListResponse,
    PilotWorkflowResponse,
    PilotWorkflowStepResponse,
)


@router.post("/pilot/workflow", summary="创建中试研究")
async def create_pilot_workflow(
    data: PilotWorkflowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    workflow_data = data.model_dump()
    workflow = await pilot_repo.create_workflow(db, workflow_data)
    await db.flush()

    # 构建响应（不含步骤）
    response_data = PilotWorkflowResponse.model_validate(workflow)
    response_data.steps = []
    return success_response(data=response_data)


@router.get("/pilot/workflow", summary="获取中试研究列表")
async def get_pilot_workflows(
    status: str | None = Query(None, description="状态筛选"),
    keyword: str | None = Query(None, description="搜索产品名称"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    workflows, total = await pilot_repo.get_workflows(
        db, status=status, keyword=keyword, page=page, page_size=page_size
    )

    # 获取每个工作流的步骤数
    items = []
    for wf in workflows:
        steps = await pilot_repo.get_workflow_steps(db, wf.id)
        completed = sum(1 for s in steps if s.status == "completed")
        item = PilotWorkflowListResponse.model_validate(wf)
        item.step_count = len(steps)
        item.completed_step_count = completed
        items.append(item)

    return paginated_response(
        data=items,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/pilot/workflow/{workflow_id}", summary="获取工作流详情")
async def get_pilot_workflow_detail(
    workflow_id: uuid_module.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    workflow = await pilot_repo.get_workflow_by_id(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")

    steps = await pilot_repo.get_workflow_steps(db, workflow_id)
    response_data = PilotWorkflowResponse.model_validate(workflow)
    response_data.steps = [
        PilotWorkflowStepResponse.model_validate(s) for s in steps
    ]
    return success_response(data=response_data)


@router.post("/pilot/workflow/{workflow_id}/start", summary="启动工作流执行")
async def start_pilot_workflow(
    workflow_id: uuid_module.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    workflow = await pilot_repo.get_workflow_by_id(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")

    if workflow.status != "pending":
        raise HTTPException(status_code=400, detail=f"工作流状态为 {workflow.status}，无法启动")

    # 异步启动工作流
    await start_workflow_engine(workflow_id)

    return success_response(data={"message": "工作流已启动", "workflow_id": str(workflow_id)})




@router.post("/pilot/workflow/{workflow_id}/approve", summary="确认当前步骤并执行下一步")
async def approve_pilot_workflow_step(
    workflow_id: uuid_module.UUID,
    current_user: CurrentUser = None,
) -> JSONResponse:
    result = await approve_step_engine(workflow_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return success_response(data=result)

@router.get("/pilot/workflow/{workflow_id}/steps/{step_id}", summary="获取步骤详情")
async def get_pilot_workflow_step(
    workflow_id: uuid_module.UUID,
    step_id: uuid_module.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    step = await pilot_repo.get_workflow_step_by_id(db, step_id)
    if not step or step.workflow_id != workflow_id:
        raise HTTPException(status_code=404, detail="步骤不存在")

    return success_response(
        data=PilotWorkflowStepResponse.model_validate(step)
    )


@router.post("/pilot/workflow/{workflow_id}/upload", summary="上传工艺文档")
async def upload_pilot_document(
    workflow_id: uuid_module.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    workflow = await pilot_repo.get_workflow_by_id(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")

    if workflow.status != "pending":
        raise HTTPException(status_code=400, detail="只有 pending 状态的工作流可以上传文档")

    # 保存文件
    upload_dir = "storage/pilot_workflow"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(
        upload_dir, f"{workflow_id}_{file.filename}"
    )
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # 更新工作流
    workflow.input_document_path = file_path
    await db.flush()

    return success_response(
        data={
            "file_path": file_path,
            "filename": file.filename,
            "file_size": len(content),
        }
    )


@router.delete("/pilot/workflow/{workflow_id}", summary="删除工作流")
async def delete_pilot_workflow(
    workflow_id: uuid_module.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    workflow = await pilot_repo.get_workflow_by_id(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")

    # Soft delete
    workflow.is_deleted = True
    workflow.updated_by = current_user.id if current_user else None
    await db.flush()

    return success_response(data={"id": str(workflow_id)})

@router.post("/literature/analyze", summary="AI 文献解析（流式）")
async def analyze_literature(
    file: UploadFile = File(...),
    current_user: CurrentUser = None,
):
    """解析上传的文献文件（PDF/TXT），提取合成路线 - SSE 流式响应"""
    import json
    import asyncio
    from app.modules.research.literature_service import analyze_literature_with_ai
    
    # 读取文件内容
    content = await file.read()
    
    # 根据文件类型提取文本
    text = ""
    filename = file.filename.lower() if file.filename else ""
    
    async def event_stream():
        nonlocal text
        
        # 进度 10%: 开始解析文件
        yield f"data: {json.dumps({'progress': 10, 'status': 'reading', 'message': '正在读取文件...'})}\n\n"
        await asyncio.sleep(0.1)
        
        try:
            if filename.endswith('.txt'):
                text = content.decode('utf-8')
            elif filename.endswith('.md') or filename.endswith('.markdown'):
                text = content.decode('utf-8')
            elif filename.endswith('.pdf'):
                # 进度 20%: 解析 PDF
                yield f"data: {json.dumps({'progress': 20, 'status': 'extracting', 'message': '正在提取 PDF 文本...'})}\n\n"
                from pypdf import PdfReader
                import io
                reader = PdfReader(io.BytesIO(content))
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            elif filename.endswith('.docx'):
                # 进度 20%: 解析 Word
                yield f"data: {json.dumps({'progress': 20, 'status': 'extracting', 'message': '正在提取 Word 文档...'})}\n\n"
                import docx
                import io
                doc = docx.Document(io.BytesIO(content))
                for para in doc.paragraphs:
                    text += para.text + "\n"
                for table in doc.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            text += cell.text + " "
                        text += "\n"
            elif filename.endswith('.doc'):
                yield f"data: {json.dumps({'progress': 100, 'status': 'error', 'error': '不支持旧版 .doc 格式，请转换为 .docx 或 PDF 后上传'})}\n\n"
                return
            elif filename.endswith('.rtf'):
                text = content.decode('utf-8', errors='ignore')
                import re
                text = re.sub(r'\\[a-z]+[\d]*\s?', '', text)
                text = re.sub(r'[{}]', '', text)
            else:
                yield f"data: {json.dumps({'progress': 100, 'status': 'error', 'error': '不支持的文件格式，请上传 PDF、Word、TXT、Markdown 或 RTF 文件'})}\n\n"
                return
        except Exception as e:
            yield f"data: {json.dumps({'progress': 100, 'status': 'error', 'error': f'文件解析失败: {str(e)}'})}\n\n"
            return
        
        # 进度 30%: 文件提取完成
        yield f"data: {json.dumps({'progress': 30, 'status': 'extracted', 'message': f'文件提取完成，共 {len(text)} 字符'})}\n\n"
        await asyncio.sleep(0.1)
        
        # 进度 40%: 开始 AI 分析
        yield f"data: {json.dumps({'progress': 40, 'status': 'analyzing', 'message': 'AI 正在分析文献，提取合成路线...'})}\n\n"
        
        try:
            # 调用 AI 解析
            result = await analyze_literature_with_ai(text)
            
            # 进度 90%: AI 分析完成
            yield f"data: {json.dumps({'progress': 90, 'status': 'analyzed', 'message': 'AI 分析完成，正在整理结果...'})}\n\n"
            await asyncio.sleep(0.1)
            
            # 进度 100%: 完成
            yield f"data: {json.dumps({'progress': 100, 'status': 'complete', 'data': result})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'progress': 100, 'status': 'error', 'error': f'AI 解析失败: {str(e)}'})}\n\n"
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ==================== 打通路线 CRUD ====================



@router.get("/routes", summary="获取打通路线列表")
async def get_routes(
    project_id: str | None = Query(None),
    status: str | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from app.modules.research.models import RouteDevelopment, RouteExperiment
    from sqlalchemy import select, func, or_
    
    query = select(RouteDevelopment).where(RouteDevelopment.is_deleted == False)
    count_query = select(func.count()).select_from(RouteDevelopment).where(RouteDevelopment.is_deleted == False)
    
    if project_id:
        query = query.where(RouteDevelopment.project_id == project_id)
        count_query = count_query.where(RouteDevelopment.project_id == project_id)
    if status:
        query = query.where(RouteDevelopment.status == status)
        count_query = count_query.where(RouteDevelopment.status == status)
    if keyword:
        pattern = f"%{keyword}%"
        like_filter = or_(
            RouteDevelopment.name.ilike(pattern),
            RouteDevelopment.route_no.ilike(pattern),
        )
        query = query.where(like_filter)
        count_query = count_query.where(like_filter)
    
    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(RouteDevelopment.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()
    
    data = []
    for item in items:
        data.append({
            "id": str(item.id),
            "project_id": item.project_id,
            "route_no": item.route_no,
            "name": item.name,
            "source": item.source,
            "source_reference": item.source_reference,
            "description": item.description,
            "status": item.status,
            "current_module": item.current_module,
            "literature_sources": item.literature_sources or [],
            "candidate_routes": item.candidate_routes or [],
            "selected_route_ids": item.selected_route_ids or [],
            "experiment_plans": item.experiment_plans or [],
            "experiments": [],  # Will be loaded separately
            "assessment": item.assessment,
            "deliverables": item.deliverables or [],
            "start_date": item.start_date.isoformat() if item.start_date else None,
            "end_date": item.end_date.isoformat() if item.end_date else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "created_by": str(item.created_by) if item.created_by else None,
        })
    
    return paginated_response(data=data, page=page, page_size=page_size, total=total)


@router.get("/routes/{route_id}", summary="获取路线详情")
async def get_route(
    route_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from app.modules.research.models import RouteDevelopment, RouteExperiment
    from sqlalchemy import select
    
    result = await db.execute(
        select(RouteDevelopment).where(
            RouteDevelopment.id == route_id,
            RouteDevelopment.is_deleted == False,
        )
    )
    route = result.scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail="路线不存在")
    
    # Load experiments
    exp_result = await db.execute(
        select(RouteExperiment).where(
            RouteExperiment.route_id == str(route.id),
            RouteExperiment.is_deleted == False,
        ).order_by(RouteExperiment.experiment_date.desc())
    )
    experiments = exp_result.scalars().all()
    
    data = {
        "id": str(route.id),
        "project_id": route.project_id,
        "route_no": route.route_no,
        "name": route.name,
        "source": route.source,
        "source_reference": route.source_reference,
        "description": route.description,
        "status": route.status,
        "current_module": route.current_module,
        "literature_sources": route.literature_sources or [],
        "candidate_routes": route.candidate_routes or [],
        "selected_route_ids": route.selected_route_ids or [],
        "experiment_plans": route.experiment_plans or [],
        "experiments": [
            {
                "id": str(exp.id),
                "route_id": exp.route_id,
                "experiment_no": exp.experiment_no,
                "title": exp.title,
                "description": exp.description,
                "date": exp.experiment_date.isoformat() if exp.experiment_date else None,
                "operator": exp.operator,
                "status": exp.status,
                "reaction_temp": exp.reaction_temp,
                "reaction_time": exp.reaction_time,
                "yield": exp.yield_pct,
                "purity": exp.purity,
                "impurities": exp.impurities,
                "result_summary": exp.result_summary,
                "created_at": exp.created_at.isoformat() if exp.created_at else None,
                "updated_at": exp.updated_at.isoformat() if exp.updated_at else None,
            }
            for exp in experiments
        ],
        "assessment": route.assessment,
        "deliverables": route.deliverables or [],
        "start_date": route.start_date.isoformat() if route.start_date else None,
        "end_date": route.end_date.isoformat() if route.end_date else None,
        "created_at": route.created_at.isoformat() if route.created_at else None,
        "updated_at": route.updated_at.isoformat() if route.updated_at else None,
        "created_by": str(route.created_by) if route.created_by else None,
    }
    
    return success_response(data=data)


@router.post("/routes", summary="创建路线")
async def create_route(
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    from app.modules.research.models import RouteDevelopment, RouteExperiment
    import uuid as uuid_mod
    from datetime import date as date_mod
    
    route = RouteDevelopment(
        id=str(uuid_mod.uuid4()),
        project_id=data.get("project_id", "default"),
        route_no=data.get("route_no", f"RD-{date_mod.today().year}-{str(uuid_mod.uuid4())[:6].upper()}"),
        name=data.get("name", "新路线"),
        source=data.get("source", "manual"),
        source_reference=data.get("source_reference"),
        description=data.get("description"),
        status="planning",
        current_module="research",
        created_by=current_user.id if current_user else None,
    )
    db.add(route)
    await db.flush()
    
    return success_response(data={"id": str(route.id), "route_no": route.route_no})


@router.put("/routes/{route_id}", summary="更新路线（保存工作流状态）")
async def update_route(
    route_id: str,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    from app.modules.research.models import RouteDevelopment, RouteExperiment
    from sqlalchemy import select
    
    result = await db.execute(
        select(RouteDevelopment).where(
            RouteDevelopment.id == route_id,
            RouteDevelopment.is_deleted == False,
        )
    )
    route = result.scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail="路线不存在")
    
    # Update fields
    updatable = [
        "name", "source", "source_reference", "description", "status",
        "current_module", "literature_sources", "candidate_routes",
        "selected_route_ids", "experiment_plans", "assessment", "deliverables",
        "end_date",
    ]
    for field in updatable:
        if field in data:
            setattr(route, field, data[field])
    
    if current_user:
        route.updated_by = current_user.id
    
    await db.flush()
    return success_response(data={"id": str(route.id), "message": "已保存"})


@router.delete("/routes/{route_id}", summary="删除路线")
async def delete_route(
    route_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    from app.modules.research.models import RouteDevelopment, RouteExperiment
    from sqlalchemy import select
    
    # 先查询路线是否存在（包括已删除的）
    result = await db.execute(
        select(RouteDevelopment).where(
            RouteDevelopment.id == route_id,
        )
    )
    route = result.scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail="路线不存在")
    
    # 如果已经删除，直接返回成功（幂等性）
    if route.is_deleted:
        return success_response(data={"message": "已删除"})
    
    route.is_deleted = True
    await db.flush()
    return success_response(data={"message": "已删除"})


# ==================== 实验记录 CRUD ====================

@router.post("/routes/{route_id}/experiments", summary="添加实验记录")
async def create_experiment(
    route_id: str,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    from app.modules.research.models import RouteDevelopment, RouteExperiment
    import uuid as uuid_mod
    from datetime import date as date_mod
    
    # Count existing experiments for this route
    from sqlalchemy import select, func
    count_result = await db.execute(
        select(func.count()).select_from(RouteExperiment).where(
            RouteExperiment.route_id == route_id,
            RouteExperiment.is_deleted == False,
        )
    )
    count = count_result.scalar_one()
    
    exp = RouteExperiment(
        id=str(uuid_mod.uuid4()),
        route_id=route_id,
        experiment_no=data.get("experiment_no", f"EXP-{count + 1:03d}"),
        title=data.get("title", "实验记录"),
        description=data.get("description"),
        experiment_date=date_mod.fromisoformat(data["date"]) if data.get("date") else date_mod.today(),
        operator=data.get("operator"),
        status=data.get("status", "planned"),
        reaction_temp=data.get("reaction_temp"),
        reaction_time=data.get("reaction_time"),
        yield_pct=data.get("yield"),
        purity=data.get("purity"),
        impurities=data.get("impurities"),
        result_summary=data.get("result_summary"),
        created_by=current_user.id if current_user else None,
    )
    db.add(exp)
    await db.flush()
    
    return success_response(data={"id": str(exp.id), "experiment_no": exp.experiment_no})


@router.put("/experiments/{exp_id}", summary="更新实验记录")
async def update_experiment(
    exp_id: str,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    from app.modules.research.models import RouteDevelopment, RouteExperiment
    from sqlalchemy import select
    from datetime import date as date_mod
    
    result = await db.execute(
        select(RouteExperiment).where(
            RouteExperiment.id == exp_id,
            RouteExperiment.is_deleted == False,
        )
    )
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="实验记录不存在")
    
    updatable = [
        "title", "description", "operator", "status",
        "reaction_temp", "reaction_time", "impurities", "result_summary",
    ]
    for field in updatable:
        if field in data:
            setattr(exp, field, data[field])
    
    if "date" in data and data["date"]:
        exp.experiment_date = date_mod.fromisoformat(data["date"])
    if "yield" in data:
        exp.yield_pct = data["yield"]
    if "purity" in data:
        exp.purity = data["purity"]
    if current_user:
        exp.updated_by = current_user.id
    
    await db.flush()
    return success_response(data={"id": str(exp.id), "message": "已保存"})


@router.delete("/experiments/{exp_id}", summary="删除实验记录")
async def delete_experiment(
    exp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    from app.modules.research.models import RouteDevelopment, RouteExperiment
    from sqlalchemy import select
    
    result = await db.execute(
        select(RouteExperiment).where(
            RouteExperiment.id == exp_id,
            RouteExperiment.is_deleted == False,
        )
    )
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="实验记录不存在")
    
    exp.is_deleted = True
    await db.flush()
    return success_response(data={"message": "已删除"})


# ============ 工艺优化 API ============

@router.get("/optimizations", summary="获取工艺优化列表")
async def get_optimizations(
    project_id: str | None = Query(None),
    status: str | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from sqlalchemy import select, func
    from app.modules.research.models import ProcessOptimization

    query = select(ProcessOptimization)
    count_query = select(func.count()).select_from(ProcessOptimization)

    if project_id:
        query = query.where(ProcessOptimization.project_id == project_id)
        count_query = count_query.where(ProcessOptimization.project_id == project_id)
    if status:
        query = query.where(ProcessOptimization.status == status)
        count_query = count_query.where(ProcessOptimization.status == status)
    if keyword:
        query = query.where(
            ProcessOptimization.name.ilike(f"%{keyword}%")
        )
        count_query = count_query.where(
            ProcessOptimization.name.ilike(f"%{keyword}%")
        )

    query = query.order_by(ProcessOptimization.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    optimizations = result.scalars().all()
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    return paginated_response(
        data=[{
            "id": str(opt.id),
            "project_id": opt.project_id,
            "route_id": opt.route_id,
            "name": opt.name,
            "description": opt.description,
            "status": opt.status,
            "current_module": opt.current_module,
            "doe_design": opt.doe_design,
            "doe_results": opt.doe_results,
            "impurity_study": opt.impurity_study,
            "crystal_form_study": opt.crystal_form_study,
            "quality_standards": opt.quality_standards,
            "scale_up_study": opt.scale_up_study,
            "final_report": opt.final_report,
            "start_date": str(opt.start_date) if opt.start_date else None,
            "end_date": str(opt.end_date) if opt.end_date else None,
            "created_at": opt.created_at.isoformat() if opt.created_at else None,
            "updated_at": opt.updated_at.isoformat() if opt.updated_at else None,
        } for opt in optimizations],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/optimizations/{optimization_id}", summary="获取工艺优化详情")
async def get_optimization(
    optimization_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from sqlalchemy import select
    from app.modules.research.models import ProcessOptimization

    result = await db.execute(
        select(ProcessOptimization).where(ProcessOptimization.id == optimization_id)
    )
    opt = result.scalar_one_or_none()
    if not opt:
        raise HTTPException(status_code=404, detail="工艺优化记录不存在")

    return success_response(data={
        "id": str(opt.id),
        "project_id": opt.project_id,
        "route_id": opt.route_id,
        "name": opt.name,
        "description": opt.description,
        "status": opt.status,
        "current_module": opt.current_module,
        "doe_design": opt.doe_design,
        "doe_results": opt.doe_results,
        "impurity_study": opt.impurity_study,
        "crystal_form_study": opt.crystal_form_study,
        "quality_standards": opt.quality_standards,
        "scale_up_study": opt.scale_up_study,
        "final_report": opt.final_report,
        "start_date": str(opt.start_date) if opt.start_date else None,
        "end_date": str(opt.end_date) if opt.end_date else None,
        "created_at": opt.created_at.isoformat() if opt.created_at else None,
        "updated_at": opt.updated_at.isoformat() if opt.updated_at else None,
    })


@router.post("/optimizations", summary="创建工艺优化")
async def create_optimization(
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    import uuid
    from datetime import date
    from app.modules.research.models import ProcessOptimization

    opt = ProcessOptimization(
        id=str(uuid.uuid4()),
        project_id=data.get("project_id"),
        route_id=data.get("route_id"),
        name=data.get("name", "新工艺优化"),
        description=data.get("description", ""),
        status="in_progress",
        current_module="doe",
        start_date=date.today(),
    )
    db.add(opt)
    await db.commit()
    await db.refresh(opt)

    return success_response(data={
        "id": str(opt.id),
        "route_id": opt.route_id,
        "name": opt.name,
        "status": opt.status,
        "current_module": opt.current_module,
    })


@router.put("/optimizations/{optimization_id}", summary="更新工艺优化")
async def update_optimization(
    optimization_id: str,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    from sqlalchemy import select
    from app.modules.research.models import ProcessOptimization

    result = await db.execute(
        select(ProcessOptimization).where(ProcessOptimization.id == optimization_id)
    )
    opt = result.scalar_one_or_none()
    if not opt:
        raise HTTPException(status_code=404, detail="工艺优化记录不存在")

    # 更新字段
    for key, value in data.items():
        if hasattr(opt, key) and key not in ("id", "created_at"):
            setattr(opt, key, value)

    await db.commit()
    await db.refresh(opt)

    return success_response(data={
        "id": str(opt.id),
        "route_id": opt.route_id,
        "name": opt.name,
        "status": opt.status,
        "current_module": opt.current_module,
    })


@router.delete("/optimizations/{optimization_id}", summary="删除工艺优化")
async def delete_optimization(
    optimization_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    from sqlalchemy import select
    from app.modules.research.models import ProcessOptimization

    result = await db.execute(
        select(ProcessOptimization).where(ProcessOptimization.id == optimization_id)
    )
    opt = result.scalar_one_or_none()
    if not opt:
        # Idempotent delete: return success even if record doesn't exist
        return success_response(data={"message": "工艺优化记录已删除"})

    await db.delete(opt)
    await db.commit()

    return success_response(data={"message": "工艺优化记录已删除"})


# ===== Pilot Workflow Endpoints =====

import uuid as _uuid
from datetime import datetime, timezone

from app.modules.research.models import PilotWorkflow, PilotWorkflowStep
from app.modules.research.schemas import (
    PilotWorkflowCreate,
    PilotWorkflowResponse,
    PilotWorkflowStepResponse,
    PilotWorkflowListItem,
)


PILOT_STEPS_TEMPLATE = [
    {"step_code": "recipe_review", "step_name": "工艺规程审核"},
    {"step_code": "equipment_check", "step_name": "设备确认"},
    {"step_code": "material_prep", "step_name": "物料准备"},
    {"step_code": "pilot_execution", "step_name": "中试执行"},
    {"step_code": "data_analysis", "step_name": "数据分析"},
    {"step_code": "report_gen", "step_name": "报告生成"},
]


@router.get("/pilot/workflow", summary="获取中试工作流列表")
async def get_pilot_workflows(
    status: str | None = Query(None, description="状态筛选"),
    keyword: str | None = Query(None, description="搜索产品名称"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from sqlalchemy import select, func, or_

    query = select(PilotWorkflow).where(PilotWorkflow.is_deleted == False)
    count_query = select(func.count()).select_from(PilotWorkflow).where(PilotWorkflow.is_deleted == False)

    if status:
        query = query.where(PilotWorkflow.status == status)
        count_query = count_query.where(PilotWorkflow.status == status)
    if keyword:
        kw = f"%{keyword}%"
        query = query.where(PilotWorkflow.product_name.ilike(kw))
        count_query = count_query.where(PilotWorkflow.product_name.ilike(kw))

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(PilotWorkflow.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    workflows = result.scalars().all()

    items = []
    for wf in workflows:
        # Count steps
        step_count_result = await db.execute(
            select(func.count()).select_from(PilotWorkflowStep).where(
                PilotWorkflowStep.workflow_id == wf.id,
                PilotWorkflowStep.is_deleted == False,
            )
        )
        step_count = step_count_result.scalar() or 0

        completed_result = await db.execute(
            select(func.count()).select_from(PilotWorkflowStep).where(
                PilotWorkflowStep.workflow_id == wf.id,
                PilotWorkflowStep.status == "completed",
                PilotWorkflowStep.is_deleted == False,
            )
        )
        completed_count = completed_result.scalar() or 0

        items.append(PilotWorkflowListItem(
            id=wf.id,
            product_name=wf.product_name,
            scale_up_ratio=wf.scale_up_ratio,
            equipment_type=wf.equipment_type,
            equipment_volume=wf.equipment_volume,
            status=wf.status,
            created_at=wf.created_at,
            step_count=step_count,
            completed_step_count=completed_count,
        ))

    return paginated_response(
        data=[item.model_dump(mode="json") for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/pilot/workflow/{workflow_id}", summary="获取中试工作流详情")
async def get_pilot_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from sqlalchemy import select

    result = await db.execute(
        select(PilotWorkflow).where(
            PilotWorkflow.id == workflow_id,
            PilotWorkflow.is_deleted == False,
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")

    # Load steps
    steps_result = await db.execute(
        select(PilotWorkflowStep).where(
            PilotWorkflowStep.workflow_id == workflow_id,
            PilotWorkflowStep.is_deleted == False,
        ).order_by(PilotWorkflowStep.step_order)
    )
    steps = steps_result.scalars().all()

    resp = PilotWorkflowResponse(
        id=workflow.id,
        project_id=workflow.project_id,
        product_name=workflow.product_name,
        scale_up_ratio=workflow.scale_up_ratio,
        equipment_type=workflow.equipment_type,
        equipment_volume=workflow.equipment_volume,
        input_document_path=workflow.input_document_path,
        input_context=workflow.input_context,
        status=workflow.status,
        final_report=workflow.final_report,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        created_by=workflow.created_by,
        updated_by=workflow.updated_by,
        steps=[PilotWorkflowStepResponse.model_validate(s) for s in steps],
    )
    return success_response(data=resp.model_dump(mode="json"))


@router.post("/pilot/workflow", summary="创建中试工作流")
async def create_pilot_workflow(
    data: PilotWorkflowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    workflow_id = f"PLT-{_uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    workflow = PilotWorkflow(
        id=workflow_id,
        project_id=data.project_id,
        product_name=data.product_name,
        scale_up_ratio=data.scale_up_ratio,
        equipment_type=data.equipment_type,
        equipment_volume=data.equipment_volume,
        input_context=data.input_context,
        status="pending",
    )
    if current_user:
        workflow.created_by = current_user.id
    db.add(workflow)

    # Create steps from template
    for idx, step_tpl in enumerate(PILOT_STEPS_TEMPLATE):
        step = PilotWorkflowStep(
            id=f"STP-{_uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            step_order=idx + 1,
            step_code=step_tpl["step_code"],
            step_name=step_tpl["step_name"],
            status="pending",
        )
        if current_user:
            step.created_by = current_user.id
        db.add(step)

    await db.commit()

    from sqlalchemy import select
    # Reload with steps
    steps_result = await db.execute(
        select(PilotWorkflowStep).where(
            PilotWorkflowStep.workflow_id == workflow_id,
            PilotWorkflowStep.is_deleted == False,
        ).order_by(PilotWorkflowStep.step_order)
    )
    steps = steps_result.scalars().all()

    resp = PilotWorkflowResponse(
        id=workflow.id,
        project_id=workflow.project_id,
        product_name=workflow.product_name,
        scale_up_ratio=workflow.scale_up_ratio,
        equipment_type=workflow.equipment_type,
        equipment_volume=workflow.equipment_volume,
        input_document_path=workflow.input_document_path,
        input_context=workflow.input_context,
        status=workflow.status,
        final_report=workflow.final_report,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        created_by=workflow.created_by,
        updated_by=workflow.updated_by,
        steps=[PilotWorkflowStepResponse.model_validate(s) for s in steps],
    )
    return success_response(data=resp.model_dump(mode="json"))


@router.delete("/pilot/workflow/{workflow_id}", summary="删除中试工作流")
async def delete_pilot_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from sqlalchemy import select

    result = await db.execute(
        select(PilotWorkflow).where(
            PilotWorkflow.id == workflow_id,
            PilotWorkflow.is_deleted == False,
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")

    workflow.is_deleted = True
    # Also soft-delete steps
    steps_result = await db.execute(
        select(PilotWorkflowStep).where(
            PilotWorkflowStep.workflow_id == workflow_id,
            PilotWorkflowStep.is_deleted == False,
        )
    )
    for step in steps_result.scalars().all():
        step.is_deleted = True

    await db.commit()
    return success_response(message="已删除")


@router.post("/pilot/workflow/{workflow_id}/start", summary="启动中试工作流")
async def start_pilot_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from sqlalchemy import select

    result = await db.execute(
        select(PilotWorkflow).where(
            PilotWorkflow.id == workflow_id,
            PilotWorkflow.is_deleted == False,
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")

    if workflow.status != "pending":
        raise HTTPException(status_code=400, detail="只有待启动状态的工作流可以启动")

    workflow.status = "running"
    # Set first step to running
    steps_result = await db.execute(
        select(PilotWorkflowStep).where(
            PilotWorkflowStep.workflow_id == workflow_id,
            PilotWorkflowStep.is_deleted == False,
        ).order_by(PilotWorkflowStep.step_order)
    )
    steps = steps_result.scalars().all()
    if steps:
        steps[0].status = "running"
        steps[0].started_at = datetime.now(timezone.utc)

    await db.commit()
    return success_response(message="工作流已启动")


@router.post("/pilot/workflow/{workflow_id}/approve", summary="确认工作流步骤")
async def approve_pilot_workflow_step(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from sqlalchemy import select

    result = await db.execute(
        select(PilotWorkflow).where(
            PilotWorkflow.id == workflow_id,
            PilotWorkflow.is_deleted == False,
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")

    steps_result = await db.execute(
        select(PilotWorkflowStep).where(
            PilotWorkflowStep.workflow_id == workflow_id,
            PilotWorkflowStep.is_deleted == False,
        ).order_by(PilotWorkflowStep.step_order)
    )
    steps = steps_result.scalars().all()

    # Find the waiting_approval step
    waiting_step = None
    for step in steps:
        if step.status == "waiting_approval":
            waiting_step = step
            break

    if not waiting_step:
        raise HTTPException(status_code=400, detail="没有待确认的步骤")

    now = datetime.now(timezone.utc)
    waiting_step.status = "completed"
    waiting_step.completed_at = now

    # Find next pending step
    next_step = None
    for step in steps:
        if step.status == "pending":
            next_step = step
            break

    if next_step:
        next_step.status = "running"
        next_step.started_at = now
        workflow.status = "running"
        result_status = "running"
    else:
        # All steps completed
        workflow.status = "completed"
        workflow.final_report = {
            "conclusion": f"{workflow.product_name} 中试研究已完成全部步骤。",
            "sections": [
                {"title": "总结", "content": f"放大倍数: {workflow.scale_up_ratio}x, 设备: {workflow.equipment_type} {workflow.equipment_volume}L"}
            ],
        }
        result_status = "completed"

    await db.commit()
    return success_response(data={"status": result_status, "message": "步骤已确认"})


@router.post("/pilot/workflow/{workflow_id}/upload", summary="上传中试文档")
async def upload_pilot_workflow_document(
    workflow_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from sqlalchemy import select
    import os

    result = await db.execute(
        select(PilotWorkflow).where(
            PilotWorkflow.id == workflow_id,
            PilotWorkflow.is_deleted == False,
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")

    # Save file
    upload_dir = "/tmp/pilot_uploads"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{workflow_id}_{file.filename}")
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    workflow.input_document_path = file_path
    await db.commit()

    return success_response(data={"path": file_path, "filename": file.filename})
