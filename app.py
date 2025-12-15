# app.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
from dotenv import load_dotenv

from gform_v2 import GoogleFormAutomation

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

app = FastAPI(title="Google Form Automation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class FormRequest(BaseModel):
    form_url: str
    headless: Optional[bool] = True

class BatchFormRequest(BaseModel):
    form_url: str
    runs: int
    headless: Optional[bool] = True
@app.post("/fill-form/")
def fill_google_form(req: FormRequest):
    """
    Fully fills AND submits the Google Form
    AND returns GPT-generated answers.
    """
    if not req.form_url:
        raise HTTPException(status_code=400, detail="Form URL is required")

    try:
        bot = GoogleFormAutomation(
            openai_api_key=OPENAI_API_KEY,
            form_url=req.form_url
        )

        # 🔥 ONE call — ALL functionality preserved
        answers = bot.fill_form()

        return {
            "status": "success",
            "message": "Form filled and submitted successfully",
            "answers": answers,
            "validation_errors": False
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "answers": {}
        }
@app.post("/fill-form/batch")
def fill_google_form_batch(req: BatchFormRequest):
    """
    Fill & submit the same Google Form multiple times
    with different GPT-generated responses.
    """
    if not req.form_url:
        raise HTTPException(status_code=400, detail="Form URL is required")

    if req.runs <= 0 or req.runs > 50:
        raise HTTPException(
            status_code=400,
            detail="runs must be between 1 and 50"
        )

    results = []
    successes = 0
    failures = 0

    for i in range(req.runs):
        try:
            bot = GoogleFormAutomation(
                openai_api_key=OPENAI_API_KEY,
                form_url=req.form_url
            )

            answers = bot.fill_form()

            results.append({
                "run": i + 1,
                "status": "success",
                "answers": answers
            })
            successes += 1

        except Exception as e:
            results.append({
                "run": i + 1,
                "status": "error",
                "error": str(e)
            })
            failures += 1

    return {
        "status": "completed",
        "total_runs": req.runs,
        "successful_submissions": successes,
        "failed_submissions": failures,
        "results": results
    }

