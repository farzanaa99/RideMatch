from fastapi import FastAPI

app = FastAPI(title="RideMatch")

@app.get("/")
def root():
    return {"message": "RideMatch API is Running!!"}