#!/usr/bin/env python3
"""
Standalone EDBO+ runner script (Python 3.9).
Called via subprocess from the main app.

Usage:
    python run_edbo.py <csv_path> <objectives_json> <modes_json> <batch_size>

Example:
    python run_edbo.py /tmp/reaction.csv '["Yield"]' '["max"]' 5

Output:
    JSON to stdout with keys: csv_data (base64 encoded CSV), row_count
"""

import sys
import os
import json
import base64
import tempfile
from pathlib import Path

# Disable PyTorch JIT to prevent compilation errors
os.environ['PYTORCH_JIT'] = '0'
os.environ['TORCH_DISABLE_JIT'] = '1'

def main():
    if len(sys.argv) != 6:
        print(json.dumps({"error": "Usage: run_edbo.py <csv_path> <objectives_json> <modes_json> <batch_size> <save_prediction>"}))
        sys.exit(1)

    csv_path = sys.argv[1]
    objectives_json = sys.argv[2]
    modes_json = sys.argv[3]
    batch_size = int(sys.argv[4])
    save_prediction = sys.argv[5].lower() == 'true'

    try:
        objectives = json.loads(objectives_json)
        modes = json.loads(modes_json)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    if not Path(csv_path).exists():
        print(json.dumps({"error": f"CSV file not found: {csv_path}"}))
        sys.exit(1)

    try:
        from edbo.plus.optimizer_botorch import EDBOplus

        # EDBO+ expects the CSV in a specific directory
        csv_dir = str(Path(csv_path).parent)
        csv_filename = Path(csv_path).name

        # Run EDBO+ optimization
        result_df = EDBOplus().run(
            objectives=objectives,
            objective_mode=modes,
            directory=csv_dir,
            filename=csv_filename,
            batch=batch_size,
            columns_features='all',
            init_sampling_method='cvt'
        )

        # Convert result to CSV string
        result_csv = result_df.to_csv(index=False)

        # Encode as base64 for safe JSON transport
        csv_b64 = base64.b64encode(result_csv.encode('utf-8')).decode('utf-8')

        # Output result
        output = {
            "csv_data": csv_b64,
            "row_count": len(result_df)
        }
        
        # Check for prediction file and include if requested
        pred_file = Path(csv_dir) / f"pred_{csv_filename}"
        if save_prediction and pred_file.exists():
            pred_csv = pred_file.read_text(encoding='utf-8')
            pred_b64 = base64.b64encode(pred_csv.encode('utf-8')).decode('utf-8')
            output["prediction_data"] = pred_b64
            output["prediction_filename"] = f"pred_{csv_filename}"

        print(json.dumps(output))

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
