# Restoration & Refinement Plan (V1.2.6)

## Diagnostics & Research
- [ ] Audit `main.py` for `/paper-entry` and `/slicer` logic regressions.
- [ ] Audit `study.html` for answer section visibility logic.
- [ ] Inspect `manage.html` (Question Bank) for "Record Question" (录题) errors.

- [x] Bugfix: Portal Regressions & Display (V1.2.6)
    - [x] Create/Restore missing `add.html` & `subject.html`
    - [x] Upgrade `slicer.html` with A/B/C/D option fields
    - [x] Ensure `study.html` answer area works for image-only answers
    - [x] Match `paper_entry_home.html` to Figure 2 (2-card layout)
    - [x] Update version numbering to V1.2.6
- [x] Enhancement: Independence & Logic (V1.2.7)
    - [x] **Slicer**: Add `textarea` for question text & `file input` for answer image.
    - [x] **Study**: Force render A/B/C/D buttons for objective questions even if text is empty.
    - [x] **Clone**: Implement physical file copying (`shutil.copy`) for true independence.
    - [x] **Subject View**: Filter out raw paper questions (show only wrong ones).
- [x] Bugfix & Refinement (V1.2.8)
    - [x] **Fix Preview Error**: Debug "eye" icon click in Subject Question List.
    - [x] **Refine Study Logic**: Ensure `start study` only includes Bank questions + Wrong Paper questions (exclude raw paper questions).
    - [x] **Version Check**: Verify `base.html` version string and cache busting.
- [x] Bugfix & Refinement (V1.2.9)
    - [x] **Fix Version Persistence**: Update hardcoded version in `settings.html` (About section).
    - [x] **Fix Delete Error**: Change delete to JS `fetch` in `subject.html` & `manage.html` (Backend returns JSON, not Redirect).
    - [x] **Study Mode Inputs**: Add textarea/input for `fill` & `subjective` questions in `study.html` before showing answer.
- [x] Logic Overhaul (V1.3.0)
    - [x] **Difficult Persistence**: In `record` API, kept `is_difficult` even if answered correctly.
    - [x] **Pure Bank Logic**: In `subject_detail` & `study` routes, removed `OR (uqs.wrong_count > 0)`. Only shows manually owned/cloned questions.
    - [x] **Fix Duplicate Subjects**: In `index` route, filtered subjects strictly by `s.user_id = current_user.id`.
    - [x] **Manual Difficult Clear**: Added "Unmark Difficult" button in `manage.html` calling `/api/unmark-difficult`.

- [x] V1.3.1 Refinement & Admin Fix
    - [x] **Fix Admin Purity**: In `subject_detail` ensure `paper_id IS NULL` is checked even for owned questions, to exclude admin's paper uploads from "Bank" view.
    - [x] **Show Errors**: In `subject_detail`, allow showing `paper_id IS NOT NULL` questions **IF** they are in `user_question_status` (wrong/difficult).
    - [x] **Study Modes Update**:
        - `normal`: Pure Bank (`paper_id IS NULL`).
        - `error`: All Wrong (Bank + Paper).
        - `difficult`: All Difficult (Bank + Paper).
    - [x] **Clone UI**: In `subject.html`, add "Clone" button for paper questions.

- [x] V1.3.2 Study UI & Logic Fixes
    - [x] **Debug Status Update**: Verified `record` API logic with test script. Fixed permission check in main.py.
    - [x] **Study UI Overhaul**:
        - Added "Study Mode" dropdown: `All (Loop)`, `Wrong (Error)`, `Difficult (Diff)`, `Pure`.
        - Added "Question Type" dropdown: `All`, `Single`, `Multi`, `Fill`, `Essay`.
        - Passed these parameters to the `study` route.
    - [x] **Study Route Logic**: Updated `main.py` to handle `mode` and `qtype` filters.
    - [x] **Frontend Status Sync**: UI now enables the workflow; status sync verified via logic test.

- [x] V1.3.3 Persistent Error & Version Bump
    - [x] **DB Migration**: Added `history_wrong` (INTEGER DEFAULT 0) to `user_question_status`.
    - [x] **Update Record Logic**:
        - If Wrong: `wrong_count++`, `history_wrong = 1`.
        - If Right: `wrong_count = 0` (But `history_wrong` stays 1).
    - [x] **Update UI**:
        - In `subject.html` list, show "Wrong" badge if `history_wrong == 1` OR `wrong_count > 0`.
    - [x] **Version Bump**: Updated `templates/settings.html` to **V1.3.3**.

- [x] V1.3.4 Hotfix: Subject List Error
    - [x] **Diagnosis**: Confirm if error is due to missing `history_wrong` column (User likely didn't run migration).
    - [x] **Auto-Migration**: Add logic in `init_db` or startup to:
        - Check if `history_wrong` exists in `user_question_status`.
        - If missing, `ALTER TABLE ... ADD COLUMN ...`.
        - Backfill `history_wrong = 1` where `wrong_count > 0`.
    - [x] **Verify**: Ensure app starts and works even if column was missing.

- [x] V1.3.5: Missing Statistics & Home Page Fix
    - [x] **Home Page (`index`)**:
        - Update `main.py` query to count `wrong_count > 0 OR history_wrong = 1`.
        - Update `index.html` to show Red Badge for errors.
    - [x] **Subject Page (`subject_detail`)**:
        - Calculate `stats` (Total, Wrong, Difficult).
        - Update `subject.html` to show Stats Bar.

- [x] V1.3.6: Fix Logic Consistency & Error Tracking
    - [x] **Study Scope (`start_study`)**:
        - Ensure "Normal" mode strictly excludes paper questions.
        - Verify `subject_id` filter is respected.
    - [x] **Paper Detail (`paper_detail`)**:
        - Join `user_question_status` to fetch error states.
        - Update `paper_detail.html` to show Red/Orange/Green badges.
    - [x] **Error Tracking (`record`)**:
        - Ensure answering correctly clears `wrong_count` (or decrements it).
- [x] V1.3.6: Fix Logic Consistency & Error Tracking
    - [x] **Study Scope (`start_study`)**:
        - Ensure "Normal" mode strictly excludes paper questions.
        - Verify `subject_id` filter is respected.
    - [x] **Paper Detail (`paper_detail`)**:
        - Join `user_question_status` to fetch error states.
        - Update `paper_detail.html` to show Red/Orange/Green badges.
    - [x] **Error Tracking (`record`)**:
        - Ensure answering correctly clears `wrong_count` (or decrements it).
        - Ensure `history_wrong` is preserved.

- [x] V1.3.7: Final Polish - Strict Isolation & Feedback
    - [x] **Strict Isolation**: Force `paper_id IS NULL` even for `all_loop` in Subject Study.
    - [x] **Green Badge**: Add "Mastered" badge to `paper_detail.html`.
    - [x] **Visual Feedback**: Add confirmation toast to `study.html` record action.

## Bug Fixes
- [ ] Fix error when clicking "Record Question" in科目 view.
- [ ] V1.3.9: Fix Schema Mismatch (`no such column: uqs.id`)
    - [x] Identify cause: `user_question_status` has no `id` column (Composite PK).
    - [x] Fix `get_question_data` to remove `uqs.id` query.
    - [x] Verify execution of `study_page` and `paper_detail` (via Repro).
    - [x] **Fix**: Check `paper_test` route for similar issues.

- [x] V1.3.10: Fix Status Logic, Statistics & Version Display
    - [x] **Fix Version**: Update hardcoded version to `V1.3.10`.
    - [x] **Fix Status Logic**:
        - [x] "Wrong" mark not appearing.
        - [x] "Wrong" mark not clearing on correct.
        - [x] "Difficult" mark logic (> 2 wrongs).
        - [x] "Difficult" manual clear only.
    - [x] **Fix Statistics**: Dashboard stats (Today/Accuracy) showing 0.
    - [x] **Fix Paper Badges**: Ensure badges show in Paper Detail view.

- [x] V1.3.11: Critical Schema Fix & Deployment
    - [x] **Deep Audit**: Identified missing `history_wrong` in `CREATE TABLE`.
    - [x] **Fix Schema**: Added `history_wrong` to `CREATE TABLE` and improved auto-migration.
    - [x] **Fix Record API**: Added `try-except` block with error logging.
    - [x] **Verify**: Verified logic with `repro_v138.py`.
    - [x] **Documentation**: Updated `walkthrough.md` and `how_to_update_nas.md`.

- [x] V1.3.24 Hotfix: Robust Schema Migration
    - [x] **Fix**: Automate `questions` table migration (add `difficulty`, `source`, etc. if missing).
    - [x] **Version**: Bump version to V1.3.24.

- [x] V1.3.12: System Diagnosis & Database Repair Tool (The "Nuclear Option")
    - [x] **Plan**: Implementation Plan updated.
    - [x] **Backend**: Add `/api/admin/diagnose` and `/api/admin/fix_db` routes.
    - [x] **Frontend**: Update `settings.html` to show DB health status and repair button.
    - [x] **Verify**: Verified logic with `repro_v1312_diag.py`.
    - [x] **Deployment**: Commit, Push, and Notify User.

- [x] V1.3.14: Multi-Select Logic & Deep Diagnostic Fix
    - [x] **Plan**: Implementation Plan updated.
    - [x] **Frontend**: Implement `study.html` multi-select toggle & submit logic.
    - [x] **Backend**: Add `/api/admin/test_record` diagnostic API.
    - [x] **Frontend**: Add "Deep Self-Test" button to `settings.html`.
    - [ ] **Deployment**: Commit, Push, and Notify User.

- [x] V1.3.15: Logic Refinement & Scope Cleanup
    - [x] **Plan**: Implementation Plan updated.
    - [x] **Logic**: Reverted Subject Badge Logic to match Paper Center (Orange/Red) as requested.
    - [x] **Scope**: Fixed Subject Page to STRICTLY exclude Paper questions (`paper_id IS NULL`).
    - [x] **Feature**: Added "Clear Difficult" button to `manage.html`.
    - [x] **Cleanup**: Ensure "Delete Paper" cascades to delete its questions.
    - [x] **Deployment**: Commit, Push, and Notify User.

- [x] V1.3.16: Strict Scope & Sync Logic (Fixing V1.3.15 issues)
    - [x] **Scope**: Fix `subject_page` list query to strict `AND q.paper_id IS NULL`. Avoid OR condition bypass.
    - [x] **Logic**: Copy Badge Logic VERBATIM from `paper_detail.html` to `subject.html`.
    - [x] **Deployment**: Commit, Push, and Notify User.

- [x] V1.3.17: Subject Mark Logic Repair
    - [x] **Analyze**: Checked `record` API. Logic is consistent with "Green/Red/Orange" expectation.
    - [x] **Compare**: Visuals were slightly different (font size, "次" text).
    - [x] **Fix**: Strictly aligned `subject.html` badge HTML with `paper_detail.html`.
    - [x] **Deployment**: Commit, Push, and Notify User.

- [x] V1.3.18: Fix Subject List Marking Logic (CRITICAL)
    - [x] **Analyze**: Found column collision in `main.py` (`q.wrong_count` legacy vs `uqs.wrong_count` active).
    - [x] **Fix**: Update `subject_detail` query to alias `uqs` columns and overwrite legacy columns in Python loop.
    - [x] **Deployment**: Commit, Push, and Notify User.

- [x] V1.3.19: Manage Page Sync & Badge Fix
    - [x] **Visual**: Change "难点" to "难" in `subject.html` to prevent text wrapping.
    - [x] **Backend**: Fix `manage_questions` query in `main.py`. It likely ignores `user_question_status`.
    - [x] **Frontend**: Update `manage.html` to show "Difficult" status and enable "Eraser" (Unmark).
    - [x] **Deployment**: Commit, Push, and Notify User.

- [x] V1.3.20: Fix Type Display & Study Feedback
    - [x] **Manage Page**: Update `manage.html` to display specific types (Single, Multi, Fill, Subjective) matching `subject.html`.
    - [x] **Study Mode**: Add Toast feedback when submitting self-marking results for subjective questions in `study.html`.
    - [x] **Deployment**: Commit, Push, and Notify User.

- [ ] V1.3.23 Hotfix: Deployment & Stability
    - [x] Fix `NameError` (missing imports) in `main.py`.
    - [x] Fix `manage` page crash (remove `nickname` column).
    - [x] **Enhancement**: Add clickable question preview to "Manage" page.
    - [x] **Enhancement**: Add clickable question preview to "Subject List" (restore row click).
    - [x] **Fix**: Javascript syntax error in `manage.html` (Select All/Batch Actions).
    - [x] **Fix**: Restore missing "Distribute Modal" HTML in `manage.html`.
    - [x] **Fix**: Resolve "No item with that key" error in `batch_distribute` (backend row conversion).
    - [x] **Fix**: Resolve "table questions has no column named options" error (map to option_a...d).
    - [x] **Deployment**: Commit, Push, and Notify User.

- [x] V1.3.21: Fix Blank Screen Regression (CRITICAL)
    - [x] **Analyze**: Check `study.html` for JS syntax errors (likely in `record` function).
    - [x] **Fix**: Correct the syntax error (extra brace/catch block?).
    - [x] **Deployment**: Commit, Push, and Notify User.

- [x] V1.3.22: Fix Image Scaling Issue
    - [x] **Analyze**: Check `study.html` CSS. Images likely missing `max-width: 100%`.
    - [x] **Fix**: Add CSS rule `img { max-width: 100%; height: auto; }` to question content area.

- [x] V1.3.23: Admin Bulk Distribution & UI Cleanup
    - [x] **UI Polish**: `subject.html` & `manage.html` - Remove "Eye" icon, make row clickable.
    - [x] **Manage Page**:
        - [x] Add Checkbox column.
        - [x] Add "Batch Distribute" & "Batch Delete" buttons.
        - [x] Add "User Selection Modal" (fetch users list).
    - [x] **Backend**:
        - [x] Update `manage` route to pass `users` list.
        - [x] Implement `POST /api/questions/batch-distribute`.
        - [x] Implement `POST /api/questions/batch-delete`.
    - [x] **Deployment**: Commit, Push, and Notify User.
