from __future__ import annotations

import json

from dermsr.datasets import load_cifar10_benchmark
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.analysis import AnalysisError, run_analysis

app = FastAPI(title="dermsr-ui")


@app.get("/api/example")
def example() -> list[dict]:
    """The paper's own verified CIFAR-10 benchmark, as a ready-to-upload
    example / schema-reference file."""
    df = load_cifar10_benchmark()
    return json.loads(df.to_json(orient="records"))


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)) -> dict:
    raw = await file.read()
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Not valid JSON: {exc}") from exc
    if not isinstance(records, list):
        raise HTTPException(status_code=400, detail="Expected a JSON array of row objects.")

    try:
        return run_analysis(records)
    except AnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
