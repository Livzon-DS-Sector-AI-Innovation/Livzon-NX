from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from typing import List, Optional
import tempfile
import pandas as pd
from pathlib import Path
from edbo.plus import EDBOplus
import shutil
import os

app = FastAPI(title="EDBO+ Optimization Service")

class OptimizeResponse(BaseModel):
    csv_data: str
    row_count: int
    prediction_data: Optional[str] = None
    prediction_filename: Optional[str] = None

@app.post("/optimize", response_model=OptimizeResponse)
async def optimize(
    file: UploadFile = File(...),
    objectives: str = Form(...),
    objective_modes: str = Form("max"),
    batch_size: int = Form(5),
    save_predictions: bool = Form(False)
):
    """
    Run EDBO+ optimization on uploaded CSV file.
    
    - **file**: CSV file with experimental data
    - **objectives**: Comma-separated list of column names to optimize
    - **objective_modes**: Comma-separated list of "max" or "min" for each objective (default: "max")
    - **batch_size**: Number of experiments to suggest (default: 5)
    - **save_predictions**: Whether to return prediction data (default: False)
    """
    temp_dir = None
    try:
        # Parse objectives and modes
        objectives_list = [o.strip() for o in objectives.split(",")]
        modes_list = [m.strip() for m in objective_modes.split(",")]
        
        # Validate inputs
        if not objectives_list or objectives_list == ['']:
            raise HTTPException(status_code=400, detail="objectives list cannot be empty")
        
        if len(objectives_list) != len(modes_list):
            raise HTTPException(
                status_code=400, 
                detail=f"objectives ({len(objectives_list)}) and objective_modes ({len(modes_list)}) must have the same length"
            )
        
        # Create temporary directory for file processing
        temp_dir = tempfile.mkdtemp()
        csv_path = Path(temp_dir) / "input.csv"
        
        # Save uploaded file
        content = await file.read()
        with open(csv_path, 'wb') as f:
            f.write(content)
        
        # Read CSV to check structure
        df = pd.read_csv(csv_path)
        # Note: We don't validate that objective columns exist here.
        # EDBO+ handles two cases:
        # 1. Initial sampling: objectives don't exist yet → EDBO+ adds them with PENDING
        # 2. Optimization: some objectives have values, some are PENDING → EDBO+ runs BO
        
        # Run EDBO+ optimization
        edbo = EDBOplus()
        result_df = edbo.run(
            objectives=objectives_list,
            objective_mode=modes_list,
            directory=temp_dir,
            filename="input.csv",
            batch=batch_size,
            columns_features='all',
            init_sampling_method='cvt'
        )
        
        # Convert result to CSV string
        csv_data = result_df.to_csv(index=False)
        row_count = len(result_df)
        
        response = OptimizeResponse(
            csv_data=csv_data,
            row_count=row_count
        )
        
        # Check for prediction file if requested
        if save_predictions:
            pred_file = Path(temp_dir) / "pred_input.csv"
            if pred_file.exists():
                pred_df = pd.read_csv(pred_file)
                response.prediction_data = pred_df.to_csv(index=False)
                response.prediction_filename = "pred_input.csv"
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"EDBO+ optimization failed: {str(e)}")
    finally:
        # Clean up temporary directory
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "edbo-plus"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
