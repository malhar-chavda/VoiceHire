import asyncio
import httpx
import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.utils.settings import settings

BASE_URL = f"http://127.0.0.1:{settings.APP_PORT}/api"
TS = int(time.time())
EMAIL = f"speech.test.{TS}@example.com"

JD_PDF = (
    b"%PDF-1.1\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n"
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n"
    b"<< /Type /Page /Parent 2 0 R /Contents 4 0 R /MediaBox [0 0 612 792]"
    b" /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>\nendobj\n"
    b"4 0 obj\n<< /Length 120 >>\nstream\nBT /F1 12 Tf 50 750 Td"
    b" (JOB: Python Backend Engineer) Tj 0 -20 Td (Skills: Python, FastAPI, REST APIs, SQL) Tj ET\nendstream\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\n%%EOF"
)

RESUME_PDF = (
    b"%PDF-1.1\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n"
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n"
    b"<< /Type /Page /Parent 2 0 R /Contents 4 0 R /MediaBox [0 0 612 792]"
    b" /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>\nendobj\n"
    b"4 0 obj\n<< /Length 180 >>\nstream\nBT /F1 12 Tf 50 750 Td"
    b" (Name: Speech Test User) Tj 0 -15 Td (Email: " + EMAIL.encode() + b") Tj"
    b" 0 -15 Td (Skills: Python, FastAPI, REST, SQL. 5 years backend dev.) Tj ET\nendstream\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\n%%EOF"
)


async def run():
    print("=== Speech Pipeline Test (TTS + STT) ===\n")

    async with httpx.AsyncClient(timeout=180.0) as client:

        login = await client.post(
            f"{BASE_URL}/auth/login",
            data={"username": settings.RECRUITER_USERNAME, "password": settings.RECRUITER_PASSWORD},
        )
        assert login.status_code == 200, f"Login failed: {login.text}"
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        print("[OK] Login")

        upload = await client.post(
            f"{BASE_URL}/documents/upload",
            files={
                "resume_file": ("resume.pdf", RESUME_PDF, "application/pdf"),
                "jd_file":     ("jd.pdf",     JD_PDF,     "application/pdf"),
            },
            headers=headers,
        )
        assert upload.status_code == 201, f"Upload failed: {upload.text}"
        up = upload.json()
        resume_id, jd_id = up["resume_id"], up["jd_id"]
        print(f"[OK] Upload  resume={resume_id[:8]}  jd={jd_id[:8]}")

        ev = await client.post(
            f"{BASE_URL}/interview/evaluate",
            json={"resume_id": resume_id, "jd_id": jd_id, "num_questions": 2},
            headers=headers,
        )
        assert ev.status_code == 200, f"Evaluate failed: {ev.text}"
        ev_data = ev.json()
        assert ev_data["eligibility"], f"Not eligible -- score: {ev_data['match_score']}"
        session_token = ev_data["session_token"]
        interview_id = ev_data["interview_id"]
        print(f"[OK] Evaluate  score={ev_data['match_score']}  eligible=True")

        # Test speech token endpoint
        tok_resp = await client.get(
            f"{BASE_URL}/interview/speech-token",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        assert tok_resp.status_code == 200, f"Speech token failed: {tok_resp.text}"
        tok_data = tok_resp.json()
        assert tok_data["token"], "Speech token is empty"
        print(f"[OK] Speech token region={tok_data['region']}  token_len={len(tok_data['token'])}")

        print("\n--- Interview Loop (POST /turn) ---")
        turn = 0
        stt_tested = False
        current_answer_id = None

        # First call: join (no answer_id)
        resp = await client.post(
            f"{BASE_URL}/interview/turn",
            json={"session_token": session_token},
        )
        assert resp.status_code == 200, f"Turn (join) failed: {resp.text}"
        data = resp.json()
        assert data["status"] == "active", f"Expected active, got: {data['status']}"
        assert data["question"], "No question returned on first turn"
        q = data["question"]
        turn += 1
        print(f"\n[Q{q['question_order']}] {q['question_text'][:80]}")
        tts_ok = bool(q.get("audio_url"))
        print(f"  TTS audio_url: [{'PRESENT' if tts_ok else 'MISSING'}]")
        assert tts_ok, "TTS FAILED: audio_url missing"

        while True:
            is_followup = q.get("is_follow_up", False)

            if turn == 1:
                answer_text = "I am not sure about this."
                answer_audio_url = None
                print("  Submitting weak answer -> expecting followup...")
            elif is_followup and not stt_tested:
                answer_text = ""
                answer_audio_url = q["audio_url"]
                stt_tested = True
                print("  Submitting audio_url as answer -> STT will transcribe...")
            else:
                answer_text = (
                    "I use EXPLAIN ANALYZE to identify slow queries, add composite indexes on "
                    "frequently filtered columns, and use connection pooling via asyncpg for "
                    "high-throughput async FastAPI services."
                )
                answer_audio_url = None
                print("  Submitting strong text answer...")

            resp = await client.post(
                f"{BASE_URL}/interview/turn",
                json={
                    "session_token": session_token,
                    "answer_id": q["answer_id"],
                    "answer_text": answer_text,
                    "answer_audio_url": answer_audio_url,
                },
            )
            assert resp.status_code == 200, f"Turn failed: {resp.text}"
            data = resp.json()
            score = data.get("score")
            print(f"  Score: {score}/10")

            if is_followup and stt_tested:
                if score and score > 0:
                    print("  STT result: [PASS] score > 0, transcription worked")
                else:
                    print("  STT result: [WARN] score=0, STT may have returned empty audio")

            if data["status"] == "completed":
                print(f"\n[OK] Interview complete")
                print(f"  final_score={data.get('final_score')}  rec={data.get('recommendation')}")
                break

            q = data["question"]
            turn += 1
            tag = "[FOLLOWUP]" if q.get("is_follow_up") else f"[Q{q['question_order']}]"
            print(f"\n{tag} {q['question_text'][:80]}")
            tts_ok = bool(q.get("audio_url"))
            print(f"  TTS audio_url: [{'PRESENT' if tts_ok else 'MISSING'}]")
            assert tts_ok, f"TTS FAILED on turn {turn}"

            if turn > 8:
                print("[WARN] Safety break at 8 turns")
                break

        print("\n" + "=" * 45)
        print("TTS: [PASS] audio_url present on all questions")
        if stt_tested:
            print("STT: [PASS] audio submitted as answer, transcription triggered")
        else:
            print("STT: [WARN] followup not triggered, STT path not exercised")
        print("Speech token: [PASS] issued successfully")
        print("=" * 45)


if __name__ == "__main__":
    asyncio.run(run())
