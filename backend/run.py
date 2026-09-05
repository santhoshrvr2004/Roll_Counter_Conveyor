import uvicorn

if __name__ == "__main__":
    # Keep a single worker: one process owns one physical RealSense camera.
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False, workers=1)
