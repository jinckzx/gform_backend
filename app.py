# # app.py
# from fastapi import FastAPI, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel
# from typing import Optional
# import os
# from dotenv import load_dotenv

# from gform_v2 import GoogleFormAutomation

# load_dotenv()
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# app = FastAPI(title="Google Form Automation API")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# class FormRequest(BaseModel):
#     form_url: str
#     headless: Optional[bool] = True

# class BatchFormRequest(BaseModel):
#     form_url: str
#     runs: int
#     headless: Optional[bool] = True
# @app.post("/fill-form/")
# def fill_google_form(req: FormRequest):
#     """
#     Fully fills AND submits the Google Form
#     AND returns GPT-generated answers.
#     """
#     if not req.form_url:
#         raise HTTPException(status_code=400, detail="Form URL is required")

#     try:
#         bot = GoogleFormAutomation(
#             openai_api_key=OPENAI_API_KEY,
#             form_url=req.form_url
#         )

#         # 🔥 ONE call — ALL functionality preserved
#         answers = bot.fill_form()

#         return {
#             "status": "success",
#             "message": "Form filled and submitted successfully",
#             "answers": answers,
#             "validation_errors": False
#         }

#     except Exception as e:
#         return {
#             "status": "error",
#             "message": str(e),
#             "answers": {}
#         }
# @app.post("/fill-form/batch")
# def fill_google_form_batch(req: BatchFormRequest):
#     """
#     Fill & submit the same Google Form multiple times
#     with different GPT-generated responses.
#     """
#     if not req.form_url:
#         raise HTTPException(status_code=400, detail="Form URL is required")

#     if req.runs <= 0 or req.runs > 50:
#         raise HTTPException(
#             status_code=400,
#             detail="runs must be between 1 and 50"
#         )

#     results = []
#     successes = 0
#     failures = 0

#     for i in range(req.runs):
#         try:
#             bot = GoogleFormAutomation(
#                 openai_api_key=OPENAI_API_KEY,
#                 form_url=req.form_url
#             )

#             answers = bot.fill_form()

#             results.append({
#                 "run": i + 1,
#                 "status": "success",
#                 "answers": answers
#             })
#             successes += 1

#         except Exception as e:
#             results.append({
#                 "run": i + 1,
#                 "status": "error",
#                 "error": str(e)
#             })
#             failures += 1

#     return {
#         "status": "completed",
#         "total_runs": req.runs,
#         "successful_submissions": successes,
#         "failed_submissions": failures,
#         "results": results
#     }

# app.py - Fixed version
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict
import os
from dotenv import load_dotenv
from gform_v2 import GoogleFormAutomation
import asyncio
import uuid
import logging

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

# In-memory storage for batch job status
batch_jobs: Dict[str, dict] = {}

logger = logging.getLogger(__name__)

class FormRequest(BaseModel):
    form_url: str
    headless: Optional[bool] = True

class BatchFormRequest(BaseModel):
    form_url: str
    runs: int
    headless: Optional[bool] = True

class BatchJobStatus(BaseModel):
    job_id: str
    form_url: str
    total_runs: int
    completed_runs: int
    successful_submissions: int
    failed_submissions: int
    status: str  # "running", "completed", "failed"
    results: list


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
async def fill_google_form_batch(req: BatchFormRequest, background_tasks: BackgroundTasks):
    """
    Start a batch job to fill & submit the same Google Form multiple times.
    Returns a job_id to track progress.
    """
    if not req.form_url:
        raise HTTPException(status_code=400, detail="Form URL is required")
    
    if req.runs <= 0 or req.runs > 50:
        raise HTTPException(
            status_code=400,
            detail="runs must be between 1 and 50"
        )
    
    # Create job ID
    job_id = str(uuid.uuid4())
    
    # Initialize job status
    batch_jobs[job_id] = {
        "job_id": job_id,
        "form_url": req.form_url,
        "total_runs": req.runs,
        "completed_runs": 0,
        "successful_submissions": 0,
        "failed_submissions": 0,
        "status": "running",
        "results": []
    }
    
    # Run in background
    background_tasks.add_task(run_batch_job, job_id, req.form_url, req.runs)
    
    return {
        "status": "started",
        "job_id": job_id,
        "message": f"Batch job started with {req.runs} runs",
        "check_status_url": f"/batch-status/{job_id}"
    }


@app.get("/batch-status/{job_id}")
def get_batch_status(job_id: str):
    """
    Check the status of a batch job.
    """
    if job_id not in batch_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return batch_jobs[job_id]


def run_batch_job(job_id: str, form_url: str, runs: int):
    """
    Background task to run multiple form submissions.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 STARTING BATCH JOB: {job_id}")
    logger.info(f"   Form URL: {form_url}")
    logger.info(f"   Total Runs: {runs}")
    logger.info(f"{'='*60}\n")
    
    for i in range(runs):
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"📝 RUN {i+1}/{runs} - Starting...")
            logger.info(f"{'='*60}")
            
            bot = GoogleFormAutomation(
                openai_api_key=OPENAI_API_KEY,
                form_url=form_url
            )
            
            # Fill the form
            answers = bot.fill_form()
            
            # Update job status
            batch_jobs[job_id]["completed_runs"] = i + 1
            batch_jobs[job_id]["successful_submissions"] += 1
            batch_jobs[job_id]["results"].append({
                "run": i + 1,
                "status": "success",
                "answers": answers
            })
            
            logger.info(f"\n✅ RUN {i+1}/{runs} - SUCCESS!")
            logger.info(f"   Progress: {i+1}/{runs} completed")
            logger.info(f"   Successes: {batch_jobs[job_id]['successful_submissions']}")
            logger.info(f"   Failures: {batch_jobs[job_id]['failed_submissions']}\n")
            
        except Exception as e:
            logger.error(f"\n❌ RUN {i+1}/{runs} - FAILED!")
            logger.error(f"   Error: {str(e)}\n")
            
            # Update job status
            batch_jobs[job_id]["completed_runs"] = i + 1
            batch_jobs[job_id]["failed_submissions"] += 1
            batch_jobs[job_id]["results"].append({
                "run": i + 1,
                "status": "error",
                "error": str(e)
            })
    
    # Mark job as completed
    batch_jobs[job_id]["status"] = "completed"
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🏁 BATCH JOB COMPLETED: {job_id}")
    logger.info(f"   Total Runs: {runs}")
    logger.info(f"   Successful: {batch_jobs[job_id]['successful_submissions']}")
    logger.info(f"   Failed: {batch_jobs[job_id]['failed_submissions']}")
    logger.info(f"{'='*60}\n")


@app.post("/fill-form/batch-sync")
def fill_google_form_batch_sync(req: BatchFormRequest):
    """
    Synchronous version - waits for all runs to complete before returning.
    ⚠️ WARNING: This will timeout for large batch sizes!
    Use /fill-form/batch (async) for better results.
    """
    if not req.form_url:
        raise HTTPException(status_code=400, detail="Form URL is required")
    
    if req.runs <= 0 or req.runs > 50:
        raise HTTPException(
            status_code=400,
            detail="runs must be between 1 and 50"
        )
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 STARTING SYNCHRONOUS BATCH")
    logger.info(f"   Total Runs: {req.runs}")
    logger.info(f"{'='*60}\n")
    
    results = []
    successes = 0
    failures = 0
    
    for i in range(req.runs):
        try:
            logger.info(f"\n📝 RUN {i+1}/{req.runs} - Starting...")
            
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
            
            logger.info(f"✅ RUN {i+1}/{req.runs} - SUCCESS! ({successes} successes, {failures} failures)")
            
        except Exception as e:
            logger.error(f"❌ RUN {i+1}/{req.runs} - FAILED: {str(e)}")
            
            results.append({
                "run": i + 1,
                "status": "error",
                "error": str(e)
            })
            failures += 1
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🏁 BATCH COMPLETED")
    logger.info(f"   Successful: {successes}/{req.runs}")
    logger.info(f"   Failed: {failures}/{req.runs}")
    logger.info(f"{'='*60}\n")
    
    return {
        "status": "completed",
        "total_runs": req.runs,
        "successful_submissions": successes,
        "failed_submissions": failures,
        "results": results
    }