from __future__ import annotations

import json

from dermsr.datasets import load_cifar10_benchmark
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.analysis import AnalysisError, run_analysis
from app.figures import render_figure

app = FastAPI(title="dermsr-ui")


async def _analyze_upload(file: UploadFile) -> dict:
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


@app.get("/api/example")
def example() -> list[dict]:
    """The paper's own verified CIFAR-10 benchmark, as a ready-to-upload
    example / schema-reference file."""
    df = load_cifar10_benchmark()
    return json.loads(df.to_json(orient="records"))


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)) -> dict:
    return await _analyze_upload(file)


@app.post("/api/export/figure")
async def export_figure(
    name: str = Query(..., description="radar | per_architecture | optimal | ranks | cd"),
    fmt: str = Query("png", alias="format", description="png | pdf"),
    file: UploadFile = File(...),
) -> Response:
    """Publication-quality (300 DPI PNG or vector PDF) re-render of one of
    the interactive charts, built with matplotlib from the same analysis
    payload the frontend already computed -- see app/figures.py."""
    payload = await _analyze_upload(file)
    try:
        data = render_figure(name, payload, fmt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    media_type = "image/png" if fmt == "png" else "application/pdf"
    headers = {"Content-Disposition": f'attachment; filename="dermsr_{name}.{fmt}"'}
    return Response(content=data, media_type=media_type, headers=headers)


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
