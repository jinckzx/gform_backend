# app.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
from dotenv import load_dotenv
from gform_v2 import GoogleFormAutomation  # your file with the class

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

app = FastAPI(title="Google Form Automation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["http://localhost:5173"] for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class FormRequest(BaseModel):
    form_url: str
    headless: Optional[bool] = True  # currently unused, but could be integrated

@app.post("/fill-form/")
def fill_google_form(req: FormRequest):
    """
    Trigger the form automation for a given Google Form URL.
    Returns GPT-generated answers JSON in the response.
    """
    if not req.form_url:
        raise HTTPException(status_code=400, detail="Form URL is required")

    try:
        # Initialize bot
        bot = GoogleFormAutomation(OPENAI_API_KEY, req.form_url)

        # Setup driver
        bot.setup_driver()
        bot.driver.get(req.form_url)

        # Extract questions
        questions = bot.extract_questions()

        if not questions:
            return {
                "status": "error",
                "message": "No questions found on the form",
                "answers": {}
            }

        # Get GPT answers
        answers = bot.get_ai_answers_batch(questions)

        # Fill the form
        bot.fill_page(questions, answers)

        # Check for validation errors (optional)
        validation_errors = bot.check_validation_errors()

        # Close driver
        bot.driver.quit()

        return {
            "status": "success",
            "message": "Form filled successfully",
            "answers": answers,
            "validation_errors": validation_errors
        }

    except Exception as e:
        return {"status": "error", "message": str(e), "answers": {}}
