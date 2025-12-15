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
