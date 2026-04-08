import sys
import os
from pprint import pprint

# Ensure the app module is importable
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.services.comparison import evaluate_candidate_match

# --- MOCK DATA ---
# Feel free to change these fields if you want to test different scenarios!
mock_resume = {
  "candidate_name": "Test Candidate",
  "candidate_email": "test@example.com",
  "skills": {
    "technical": ["Python", "SQL", "FastAPI", "Git"]
  },
  "work_experience": [
    {
      "company": "Tech Startup",
      "title": "Backend Engineer",
      "duration_months": 36,
      "technologies_used": ["Python", "FastAPI", "PostgreSQL"]
    }
  ],
  "education": [
    {
      "degree": "Bachelor of Science",
      "field": "Computer Science"
    }
  ]
}

mock_jd = {
  "title": "Senior Backend Developer",
  "required_skills": ["Python", "FastAPI", "Kubernetes", "AWS", "SQL"],
  "preferred_skills": ["GraphQL", "Docker"],
  "experience_required": {
    "min_years": 4,
    "level": "Senior"
  }
}

if __name__ == "__main__":
    print("Sending mock Resume and JD to Azure OpenAI for matching...")
    print("----------------------------------------------------------")
    
    try:
        result = evaluate_candidate_match(mock_resume, mock_jd)
        
        print("\n[SUCCESS] MATCH EVALUATION SAVED:\n")
        pprint(result, indent=2, sort_dicts=False)
        
    except Exception as e:
        print(f"\n[ERROR] Error during evaluation: {e}")
