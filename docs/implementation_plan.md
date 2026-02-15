# V1.3.6: Logic Consistency & Error Fixes

## Problem
1.  **Scope Leak**: "Start Study" in Subject view includes paper questions, even though the list view excludes them. User wants strict isolation.
2.  **Missing Status**: `paper_detail` view doesn't show which questions I got wrong.
3.  **Sticky Errors**: Correcting a wrong question doesn't update the "Current Wrong" status (it stays red).

## Solution

### 1. Fix Study Scope (Strict Isolation)
-   **Goal**: If I'm in a Subject, "Start Study" (Default Mode) should ONLY show questions from that Subject's "Bank" (Paper ID is NULL), matching the list view.
-   **Change**: Update `study_page` query.
    -   Current: `query += " AND (q.user_id = ? AND q.paper_id IS NULL)"` (Wait, this looks correct in line 416? notes say "User said... it comes out all". I need to verify if `subject_id` is being enforced).
    -   **Correction**: Line 416 `q.paper_id IS NULL` IS correct for "Normal" mode.
    -   *Hypothesis*: The user might be clicking "All Loop" or "Error" mode? Or maybe the "Start Study" button passes a different mode?
    -   *Investigation*: The "Start Study" button in `subject.html` (line 31) calls `startStudy()`. `startStudy` reads `#studyMode`.
    -   *Fix*: Ensure "Normal" mode strictly enforces `paper_id IS NULL`. Ensure "All Loop" is clearly defined (maybe User DOESN'T want paper questions even there?).
    -   *Refinement*: User says "List didn't show paper questions" -> "Study showed them".
    -   *Action*: I will Ensure `subject_id` is strictly enforced and `paper_id IS NULL` is enforced unless explicitly requested.

### 2. Fix Paper Detail Status
-   **Goal**: In `/paper/{pid}`, show Red/Green badges for questions I've done.
-   **Change**: Update `paper_detail` route to join `user_question_status`.
    -   `LEFT JOIN user_question_status uqs ...`
    -   Pass `wrong_count` / `history_wrong` to template.
    -   Update `paper_detail.html` to show badges.

### 3. Fix Error Status Update (Decrement Logic)
-   **Goal**: If I answer CORRECTLY, `wrong_count` should decrease (or reset to 0 for "Current Status"), but `history_wrong` stays 1.
-   **Change**: Update `api_record_study`.
    -   Current (Line 707): `cur.execute("UPDATE user_question_status SET wrong_count = 0 ...")`
    -   *Wait*, it DOES set `wrong_count = 0`.
    -   *User Complaint*: "Statistics inaccurate... once wrong, always wrong?"
    -   *Hypothesis*: Maybe the frontend isn't updating? Or maybe `wrong_count` isn't being used for the badge?
    -   *Correction*: The badge uses `wrong_count > 0`. If I set it to 0, the Red Badge should vanish (becoming Green or Orange).
    -   *Alternative*: Maybe the user wants `wrong_count` to decrement (`max(0, count-1)`) instead of hard reset?
    -   *User Reference*: "Single account version... marking logic."
    -   *Action*: I will switch to `wrong_count = max(0, wrong_count - 1)` to be safe, OR keep `0` if that's standard. But key is ensuring `history_wrong` is PRESERVED.
    -   *Critical Fix*: I suspect the "Subject List" statistics (V1.3.5) might be caching or using a query that doesn't refresh immediately? No, it's server side.
    -   *Real Issue*: The user might be referring to the *Study Session* progress bar? Or the *Subject List* badge?
    -   *Decision*: I will explicitly set `wrong_count = 0` on correct answer (which IS the current logic, odd). I will double check line 707.
    -   *Wait*: User says: "missed ones, when done right again, stats don't update."
    -   *Maybe*: The query `UPDATE ... SET wrong_count = 0` is failing? Or `user_id` mismatch?
    -   *Refining*: I will add `history_wrong = 1` even on correct answer IF `wrong_count > 0`? No, that's backfilling.

## Planned Changes
1.  **`start_study_session`**: Verify and strict-ify filters.
2.  **`paper_detail`**: Add `user_question_status` join.
3.  **`api_record`**: Verify logic. Maybe `wrong_count` needs to be `wrong_count - 1`?
    -   *Actually*: If I answer right, it IS correct now. Why keep it red? The user says "It doesn't update".
    -   *Potential Bug*: The `record` API might be erroring out silently or logic is flawed.
    -   *Fix*: I will verify the SQL.

-   Test Record -> Answer Correct -> Badge Disappears.

## [V1.3.9] Urgent Fix: Schema Mismatch & 500 Errors

### Problem
User reported `no such column: uqs.id` in Study, Paper Detail, and 500 Error in Start Test.
This confirms `user_question_status` table in production (and likely definition) uses a Composite Primary Key `(user_id, question_id)` and has NO `id` column.

### Solution
1.  **Fix `get_question_data`**: Remove selection of `uqs.id`. Use `uqs.user_id` or query result existence to determine `has_record`.
2.  **Fix `paper_test`**:
    *   It calls `get_question_data`, so it was crashing.
    *   Add `try-except` block for safety.
    *   Ensure robust query logic.

### Verification
-   **Repro Script**: Updated `repro_v138.py` to use schema WITHOUT `id` column. Verified `get_question_data` works.
-   **Repro Script**: Updated `repro_v138.py` to use schema WITHOUT `id` column. Verified `get_question_data` works.
-   **Manual**: User to verify "Study", "View Paper", and "Start Test" no longer crash.

## [V1.3.10] Fix Status Logic, Statistics & Version Display

### Problems
1.  **Version**: Still shows V1.3.7.
2.  **Status Logic**: "Wrong" and "Difficult" marks not appearing/updating correctly.
    *   Likely due to `INSERT OR IGNORE` not initializing `wrong_count` properly or `UPDATE` logic failing on fresh rows.
    *   Manual clear for "Difficult" is requested.
3.  **Statistics**: Dashboard shows 0 for today/accuracy.
    *   `date('now')` uses UTC. User is in UTC+8.
4.  **Paper Badges**: Not showing in Paper Detail.

### Solution
1.  **Version**: Update `base.html` to `V1.3.10`.
2.  **Status Logic (`record` API)**:
    *   Explicitly check if row exists. If not, `INSERT`.
    *   If correct: `wrong_count = 0`.
    *   If wrong: `wrong_count += 1`, `history_wrong = 1`.
    *   If `wrong_count >= 2`: `is_difficult = 1`.
3.  **Statistics (`index`)**:
    *   Use `date('now', 'localtime')` for SQLite queries to match system time.
4.  **Paper Badges**: Verified `paper_detail.html` has logic, but `get_question_data` might need to ensure it returns these fields for *paper* questions too (it does, but I'll double check).

### Verification
-   **Repro Script**: Add test cases for `record` API (wrong -> wrong -> difficult).
-   **Manual**: User verifies dashboard stats and status badges.

## [V1.3.12] System Diagnosis & Repair Tool (The "Nuclear Option")

### Problem
V1.3.11 update applied successfully (version changed), but defects persist. This implies the **Auto-Migration** in `init_db` failed silently or didn't commit changes to the persistent volume strings. We are flying blind without logs.

### Solution: Visibility & Manual Control
Instead of guessing, we will add a **Diagnostics Dashboard** to `settings.html`.

#### 1. Backend (`main.py`)
- **New Route**: `GET /api/admin/diagnose`
    - Checks `PRAGMA table_info` for `user_question_status`.
    - Returns: `{"status": "ok" | "error", "missing_columns": ["history_wrong"], "db_path": "...", "writable": bal}`.
- **New Route**: `POST /api/admin/fix_db`
    - Forces `ALTER TABLE`.
    - Forces permissions check.
    - Returns success/fail log.

#### 2. Frontend (`templates/settings.html`)
- Add a "System Health" card.
- Auto-check on load.
- If `history_wrong` is missing -> Show **RED ALERT** and a **"FIX DATABASE"** button.

### Verification
User will:
1. Update to V1.3.12.
2. Go to Settings.
3. See "Database Error: Missing Column".
4. Click "Fix".
5. See "Success".
6. Problem Solved.

## [V1.3.14] Multi-Select Logic & Deep Diagnostic Record Test

### Problems
1.  **Multi-Select Bug**: Clicking "A" for an "AD" question immediately marks it wrong. `checkOpt` handles all types as single-click.
2.  **Persistent Record Failure**: "Fix Database" might have fixed the schema, but user says marking "still doesn't work". This suggests a logic error or deeper constraint violation that `PRAGMA table_info` doesn't reveal.

### Solution

#### 1. Frontend Logic (Multi-Select)
-   Modify `study.html`:
    -   Add `selectedOpts = Set()`.
    -   If `q.question_type == 'multi'`:
        -   Clicking toggles `selectedOpts`.
        -   Show "Submit Answer" button.
        -   Submit checks if `sorted(selectedOpts) == sorted(correct_answer)`.
    -   If `single`: Keep instant feedback.

#### 2. Deep Diagnostic (Write Test)
-   Enhance `settings.html` Diagnosis Card:
    -   Add "Run Deep Self-Test" (深度自检) button.
-   Add Backend Route `/api/admin/test_record`:
    -   Inserts a dummy record into `user_question_status`.
    -   Updates it (simulating wrong -> wrong).
    -   Deletes it.
    -   Captures **exact SQL error**.
    -   Returns: `{"status": "ok" | "error", "log": "..."}`.

### Verification
-   **Manual**: User runs "Deep Self-Test" and screenshot the log if it fails.
-   **Manual**: User tries multi-select question (A -> D -> Submit).
### Automated Tests - Exact commands you'll run, browser tests using the browser tool, etc.
- Run `repro_diag.py` to confirm deep diagnostics.
- Verify multi-select behavior in browser (Toggle + Confirm).

## V1.3.15: Logic Refinement & Scope Cleanup
### Subject Study Mode Correctness
- **Problem**: Users correcting a wrong answer in Subject Mode still see "曾错" (History Wrong) instead of "Mastered", creating confusion. Paper questions also leak into Subject Mode.
- **Fix**: 
    - Frontend: `templates/subject.html` -> Shows "Mastered" (Green) if `wrong_count == 0` (Active Correct), hiding history.
    - Backend: `main.py` -> `start_study` filters `paper_id IS NULL` for Subject Mode.
    - Cleanup: `delete_paper` cascades delete to questions table.

### Verification
- **Manual**: Deploy and check if correcting a red-marked question turns it Green immediately.
- **Manual**: Check if Paper Center questions appear in Subject List (they should not).

## V1.3.16: Strict Scope & Sync Logic
### Scope Fix
- **Problem**: V1.3.15 fix was incomplete due to OR condition bypassing the `paper_id IS NULL` check in `subject_page` list query. Also `study` route had a duplicate block.
- **Fix**: Strict `AND q.paper_id IS NULL` in `subject_page` query and fix `study` route.

### Logic Sync
- **Problem**: User reports Subject Study marking logic doesn't match Paper Center "Perfect" logic.
- **Fix**: 
    - Identify `has_record` logic from `get_question_data`.
    - Add `has_record` to `subject_page` query (likely checking if `uqs.question_id` is not null).
    - Update `subject.html` badge logic to match `paper_detail.html` verbatim.

### Verification
- **Manual**: Deploy. Check Subject List for paper questions (should be gone).
- **Manual**: Check "Green" badge logic (Mastered) matches Paper Center.

## V1.3.17: Mark Logic Repair
### Visual Sync
- **Problem**: User feels Subject Badge logic differs from Paper Center.
- **Fix**: STRICT copy-paste of badge HTML from `paper_detail.html` (font-size 0.7rem, remove "次").
- **Backend Refinement**: Verified `record` API correctly handles `wrong_count` and `history_wrong`.

### Verification
- **Manual**: Check Subject List badges against Paper Center badges. They should be identical in style and logic.

## V1.3.18: Fix Subject List Marking Logic
### Root Cause
- **Collision**: `main.py` query for `subject_detail` selected `q.*` and `uqs.wrong_count`.
- **Legacy Schema**: `questions` table has a legacy `wrong_count` column (unused/empty).
- **Bug**: `dict(row)` likely prioritized the legacy empty column over the active `uqs` column, causing "Marking Logic" to fail (always 0).

### Fix
- **Backend**: Update `subject_detail` SQL to alias `uqs.wrong_count` as `user_wrong_count`.
- **Processing**: In Python loop, explicitly overwrite `d['wrong_count']` with `d['user_wrong_count']` if it exists.
- This replicates the logic in `get_question_data` used by Paper Center.

### Verification
- **Manual**: Do a question in Subject Mode -> Get Wrong -> Return to List -> MUST see Red Badge.

## V1.3.19: Manage Page Sync & Badge Fix
### Visual
- **Badge**: Change "难点" to "难" in `subject.html` to avoid two-line wrapping.
- **Manage Page**: Add "难" badge to Questions Table in `manage.html` for easy ID.

### Logic (Sync)
- **Problem**: `manage_questions` route in `main.py` had the same "Column Collision" bug as Subject List. It selected `q.*` and `uqs.is_difficult`, but `dict(r)` prioritized `q.is_difficult` (legacy/0) over `uqs`.
- **Fix**: Alias `uqs.is_difficult` as `user_is_difficult` in SQL, and explicitly overwrite `d['is_difficult']` in Python loop.

### Verification
- **Manual**: Check Subject List. Badge should be single char "难".
- **Manual**: Go to Manage Page. Questions marked difficult during study should now show "Eraser" button and "难" badge.
- **Manual**: Click "Eraser". It should remove the status.

## V1.3.20: Fix Type Display & Study Feedback
### Manage Page (Type Display)
- **Visual**: Update `manage.html` to use detailed type mapping (Single, Multi, Fill, Big) matching `subject.html`.
- **Logic**: Use `q.question_type` checks (`objective`, `multi`, `fill`) instead of `select` vs `other`.

### Study Mode (Feedback)
- **UX**: Update `record()` function in `study.html`.
- **Logic**: Add `showToast` on successful `fetch`. "🎉 已标记为正确/掌握" or "已标记为错误/难点".
- **Benefit**: User gets immediate feedback when visually marking subjective questions.

### Verification
- **Manual**: Check Manage Page. "Type" column should now show "单选", "填空" etc. instead of generic text.
- **Manual**: Study a subjective question. Click "Correct". Should see Toast "🎉 ...".

## V1.3.21: Fix Blank Screen Regression (CRITICAL)
### Root Cause
- **Syntax Error**: In V1.3.20 update to `study.html`, an extra `}` and misplaced `console.error(e)` (outside catch block) were introduced in the `record()` function.
- **Impact**: Parse error caused the entire `study.html` script to fail, resulting in blank screens for Study/Preview/Exam.

### Fix
- **Correction**: Cleaned up the `record()` function in `study.html`, ensuring proper `try/catch` structure and braces.

### Verification
- **Manual**: Refresh Study/Preview page. Content should appear immediately.
- **Manual**: Test "Correct/Wrong" buttons to ensure `record()` works and shows Toast.

## V1.3.22: Fix Image Scaling Issue
### Root Cause
- **CSS**: Images in `study.html` (Preview/Exam) lacked `max-width: 100%` constraint.
- **Impact**: Large images overflowed the container, requiring horizontal scrolling or cropping content.

### Fix
- **CSS**: Added `#question-images img, #answer-images img { max-width: 100%; height: auto; }` to `study.html`.
- **Polish**: Added `border-radius` and `box-shadow` for better aesthetics.

### Verification
- **Manual**: Open a question with a large image in Study Mode.
- **Expectation**: Image should be resized to fit the width of the question card.

## V1.3.23: Admin Bulk Distribution & UI Cleanup
### UI Changes
- **Click-to-Preview**: In `subject.html` and `manage.html`, clicking the question content (or row) should jump to preview. Remove the "Eye" icon column/button.
- **Batch Selection**: Add checkbox column to `manage.html`.
- **Batch Actions**: Add a toolbar in `manage.html` with:
    - **Distribute to User**: Opens a modal to select a target user.
    - **Batch Delete**: Deletes selected questions.

### Backend Changes (`main.py`)
- **Route Update**: Update `manage` route to fetch all users (for the distribution modal).
- **New Endpoint**: `POST /api/questions/batch-distribute`
    - Body: `{ question_ids: [], target_user_id: int }`
    - Logic: For each QID, create a copy for `target_user_id`.
- **New Endpoint**: `POST /api/questions/batch-delete`
    - Body: `{ question_ids: [] }`
    - Logic: Delete valid questions.

### Verification
- **Manual**: Go to Manage Page. Select 2 questions. Click "Distribute". Select a student. Click OK.
- **Manual**: Log in as that student. Check "Subject Bank". Questions should be there.
- **Manual**: Select questions. Click "Delete". They should disappear.
- **Manual**: Click a question row in Subject List. Should open preview.
