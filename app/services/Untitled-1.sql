-- drop table "public"."questions";
SELECT*FROM "public"."job_description";
SELECT*FROM interview;
SELECT*FROM answer;
SELECT*FROM resume;
SELECT*FROM job_description;
SELECT*FROM final_report;

TRUNCATE TABLE resume;
TRUNCATE TABLE interview;



DROP TABLE IF EXISTS answers CASCADE;

DROP TABLE answers;

ALTER TABLE final_report 
DROP COLUMN strengths,
DROP COLUMN weaknesses,
DROP COLUMN topics_not_covered,
DROP COLUMN recruiter_notes;

ALTER TABLE answer
DROP COLUMN audio_blob_url;

SELECT id FROM resume WHERE id = '72429746-8038-4e22-93ad-8cfb39358387';
SELECT id FROM job_description WHERE id = '72077c4a-a6d6-4860-940f-2409198a9b99';