"""Deterministic IPC summaries; no autonomous quality responsibility decisions."""

from app.modules.production.ipc_schemas import IpcAnalysisInput, IpcAnalysisResult


class IpcAnalysisService:
    @staticmethod
    def summarize(data: IpcAnalysisInput) -> IpcAnalysisResult:
        ph_values = [sample.ph for sample in data.samples if sample.ph is not None]
        sugar_values = [
            sample.residual_sugar
            for sample in data.samples
            if sample.residual_sugar is not None
        ]
        return IpcAnalysisResult(
            sample_count=len(data.samples),
            seed_count=sum(sample.stage == "seed" for sample in data.samples),
            fermentation_count=sum(
                sample.stage == "fermentation" for sample in data.samples
            ),
            tank_count=len({sample.tank for sample in data.samples}),
            ph_min=min(ph_values, default=None),
            ph_max=max(ph_values, default=None),
            residual_sugar_min=min(sugar_values, default=None),
            residual_sugar_max=max(sugar_values, default=None),
        )
