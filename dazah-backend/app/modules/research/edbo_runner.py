import httpx
import os

EDBO_SERVICE_URL = os.getenv("EDBO_SERVICE_URL", "http://edbo-service:8000")

async def run_edbo_optimization(
    csv_content: str,
    objectives: list,
    objective_modes: list,
    batch_size: int = 5,
    save_prediction: bool = False,
) -> dict:
    """
    Run EDBO+ optimization by calling the EDBO+ service.
    Returns dict with keys: csv_data, row_count, prediction_data, prediction_filename
    """
    async with httpx.AsyncClient(timeout=300.0) as client:
        files = {
            "file": ("input.csv", csv_content.encode(), "text/csv")
        }
        
        # EDBO service expects form data
        data = {
            "objectives": ",".join(objectives),
            "objective_modes": ",".join(objective_modes),
            "batch_size": str(batch_size),
            "save_prediction": str(save_prediction).lower()
        }
        
        response = await client.post(
            f"{EDBO_SERVICE_URL}/optimize",
            files=files,
            data=data
        )
        
        if response.status_code != 200:
            raise RuntimeError(f"EDBO+ service error: {response.text}")
        
        return response.json()
