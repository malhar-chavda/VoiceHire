import sys
import os
import json
import secrets
from fastapi.testclient import TestClient
from fpdf import FPDF

# Must add current dir to sys path for absolute imports inside the app to work seamlessly in this script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import app

def generate_pdf(filename: str, text: str):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, txt=text)
    pdf.output(filename)

def run_tests():
    print("Generating Dummy PDFs...")
    
    jd_filename = "dummy_jd.pdf"
    resume_filename = "dummy_resume.pdf"
    
    generate_pdf(jd_filename, "Company looking for a Senior Python Developer with 5 years experience, FastAPI, PostgreSQL, and Azure Cloud deployment.")
    
    rand_email = f"test_{secrets.token_hex(4)}@example.com"
    generate_pdf(resume_filename, f"John Doe. Email: {rand_email}. 10 years of experience in Python, FastAPI, PostgreSQL, and Azure Cloud deployment. Expert in all JD requirements.")

    print("Initializing test client...")
    
    try:
        # Wrap in with block to trigger the FastAPI Lifespan (connecting to DB, creating tables)
        with TestClient(app) as client:
            print("\n[STEP 1] FastAPI Lifespan triggered successfully!")

            # 1. Upload Job Description
            print("\n[STEP 2] Uploading dummy PDF Job Description...")
            with open(jd_filename, "rb") as f:
                files = {
                    "file": (jd_filename, f, "application/pdf")
                }
                res_jd = client.post("/job-descriptions/upload", files=files)
            
            if res_jd.status_code != 201:
                print(f"FAILED JD Upload. Status: {res_jd.status_code}, Detail: {res_jd.text}")
                return
            
            jd_id = res_jd.json().get("jd_id")
            print(f"SUCCESS: Job Description created with UUID: {jd_id}")

            # 2. Upload Resume
            print("\n[STEP 3] Uploading dummy PDF Resume...")
            with open(resume_filename, "rb") as f:
                files_resume = {
                    "file": (resume_filename, f, "application/pdf")
                }
                res_resume = client.post("/resumes/upload", files=files_resume)
            
            if res_resume.status_code != 201:
                print(f"FAILED Resume Upload. Status: {res_resume.status_code}, Detail: {res_resume.text}")
                return
            
            resume_id = res_resume.json().get("resume_id")
            print(f"SUCCESS: Resume created with UUID: {resume_id}")

            # 3. Evaluate Match
            print(f"\n[STEP 4] Evaluating candidate match (this triggers LLM matching AND question generation)...")
            payload = {
                "resume_id": resume_id,
                "jd_id": jd_id
            }
            res_eval = client.post("/api/interview/evaluate", json=payload)
            
            if res_eval.status_code != 200:
                print(f"FAILED Evaluation. Status: {res_eval.status_code}, Detail: {res_eval.text}")
                return
            
            eval_data = res_eval.json()
            print(f"SUCCESS: Match Evaluated!")
            print(json.dumps(eval_data, indent=2))
            
            print("\n[RESULT] All built endpoints succeeded! Application backend is fully validated.")

    except Exception as e:
        print(f"Exception during testing: {e}")

if __name__ == "__main__":
    run_tests()
