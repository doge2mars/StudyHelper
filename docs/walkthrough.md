# Study Helper Pro V1.3.27 Walkthrough

## 🛠️ V1.3.27: Restoration of "Unmark Difficult"
- **Fixed Issue**: Restored the "Unmark Difficult" (去除难点) button in Question Bank Management, which was accidentally removed.
- **Usage**: Click the yellow star button <i class="fas fa-star-half-alt"></i> in `manage.html` to remove the difficult status.

## 🚀 V1.3.26: Smart Distribution & Stats
- **Smart Tech**: Prevents duplicate distribution. If a target user already has the valid question, it is skipped.
- **Detailed Report**: Shows a summary popup with Total, Success, Duplicate, and Failed counts after distribution.
- **Backend**: Updated `/api/batch-distribute` to return detailed stats.

## 🚀 V1.3.23: Admin Bulk Distribution & UI Cleanup
- **Batch Actions**: Added checkboxes to the **Manage** page. Admins can now **Batch Delete** or **Batch Distribute** questions.
- **Distribution System**: Admins can select multiple questions and clone them directly to a specific student's subject bank (automatically matching or creating the subject).
- **UI Polish**: Removed the "Eye" button. You can now click anywhere on a question row to preview it (in Subject List and Manage Page).
- **Cleaner Interface**: Action buttons in Manage page are now context-aware (appear when items selected).
- **Bug Fixes**: Resolved `NameError` crash on startup and `manage` page crash due to schema mismatch.

## 🚀 V1.3.22: Fix Image Scaling
- **Visual Fix**: Fixed issue where large images in Study/Preview mode would overflow or crop. Added responsive CSS (`max-width: 100%`) to ensure images fit perfectly within the card.

## 🚀 V1.3.21: Fix Blank Screen Regression
- **Critical Fix**: Resolved a JavaScript syntax error in `study.html` that caused Study/Preview/Exam pages to load as blank screens. The `record()` function had a malformed try/catch block.

## 🚀 V1.3.20: Fix Type Display & Study Feedback
- **Manage Page**: Updated "Type" column to show detailed question types (Single, Multi, Fill, Subjective) instead of generic text.
- **Study Mode**: Added visual Toast feedback when self-marking subjective questions.

## 🚀 V1.3.19: Manage Page Sync & Badge Fix
- **Subject Badge**: Changed "难点" to "难" (single char) to prevent text wrapping.
- **Manage Page**: Fixed query to correctly show "Difficult" status and added "Eraser" button for these questions.

---

# Study Helper Pro V1.3.15 Walkthrough

## 🚀 V1.3.15 Release: Logic & Scope Refinement

This version addresses logic issues where "Wrong" status persisted even after correcting the mistake, and prevents Paper questions from polluting the Subject study mode.

### 1. Subject Logic & Scope Fixed
- **Scope Purity**: "Subject Entry" (List & Study) now **STRICTLY** excludes questions from Papers/Trial Center. It only shows questions manually added to the Subject Bank.
- **Badge Logic**: The "Wrong/Correct" status logic now matches the **Paper Center** exactly (Red = Current Wrong, Orange = History Wrong, Green = Mastered).
- **Manage**: Added a dedicated **"Eraser" button (Clear Difficult)** in Question Bank Management (`/manage`) to remove "Difficult" or "Wrong" status manually.

### 2. Scope Cleanup
- **Paper vs Subject**: Questions from **Papers** (Trial Center) will NO LONGER appear in the standard **Subject Study Mode** (Start Study button).
- **Start Study**: Now strictly pulls from the "Subject Bank" (manually added questions).
- **Delete Paper**: Deleting a paper now correctly deletes all its questions, preventing "orphan" questions from cluttering the system.

---

# Study Helper Pro V1.3.14 Walkthrough

## 🚀 V1.3.14 Release: Multi-Select Logic & Deep Diagnostics

This release fixes the multi-select interaction bug and provides a deeper diagnostic tool for persistent database issues.

### 1. Multi-Select Questions
- **Old Behavior**: Clicking "A" for an "AD" answer instantly marked it wrong.
- **New Behavior**: 
    - Click options to **Toggle** them (Highlight/Unhighlight).
    - Click **"Confirm Answer"** (确认答案) to submit.
    - Only then will it be judged.

### 2. Deep Self-Test (System Diagnosis)
- **Location**: Settings -> System Control Center.
- **New Button**: **"Run Deep Self-Test" (运行深度自检)**.
- **Function**:
    - Tries to Write, Read, Update, and Delete a test record in the database.
    - **Logs**: If it fails, it prints the EXACT error message (e.g. "ReadOnly", "Constraint Failed") to the screen.
    - **Use Case**: If "Fix Database" says success but marking still fails, run this and send me the screenshot.

---

# Study Helper Pro V1.3.12 Walkthrough

## 🚀 V1.3.12 Update: System Diagnosis & Repair Tool

This update introduces a "Nuclear Option" to definitively solve database schema issues that might have persisted due to deployment environments.

### 1. System Diagnosis Dashboard
- **Location**: `Settings` -> `System Control Center`.
- **Function**: Automatically checks if your database is healthy (specifically looking for the missing `history_wrong` column).
- **Alert**: If an issue is found, a **RED ALERT** card appears instantly.

### 2. One-Click Repair
- **Action**: Click the **"立即强制修复数据库" (Fix Database Now)** button in the alert card.
- **Result**:
    - Forces the database schema update.
    - specific logs show you exactly what happened.
    - **No command line needed**.

---

# Study Helper Pro V1.3.11 Walkthrough

## 🚀 V1.3.11 Update: Critical Schema Fix (Sticky Status)

This update fixes the "Sticky Wrong Status" bug where questions were not being marked as Wrong or Difficult, and statistics remained at zero.

### 1. Fixed Status Recording
- **Root Cause**: The database was missing the `history_wrong` column in some installations due to a silent migration failure.
- **Fix**:
    - **Robust Auto-Repair**: On startup, the system now explicitly checks and adds the missing column.
    - **Error Logging**: If recording fails, it now logs the exact error to the console for easier debugging.
- **Result**:
    - "Wrong" marks now correctly appear and persist.
    - "Difficult" badges appear after 2 wrong attempts.
    - Statistics (Today's Done, Accuracy) now update correctly.

### 2. Version Display
- **Version**: Updated to `V1.3.11` in the footer.

---

# Study Helper Pro V1.3.10 Walkthrough

## 🚀 V1.3.10 Update: Status Logic & Statistics Fixed

This update addresses critical bugs in status tracking and dashboard statistics.

### 1. Correct Status Logic
- **"Wrong" Mark**: Now correctly appears when you answer a question incorrectly.
- **"Difficult" Mark**: Automatically applied if you get a question wrong **2 or more times** (Active Wrong Count).
- **Auto-Clear**: Answering correctly **immediately clears** the "Wrong" mark (Active Count -> 0), but keeps the "History" mark (Orange Badge).
- **Manual Clear**: "Difficult" mark can be manually cleared in the "Question Bank Management" section.

### 2. Accurate Dashboard Statistics
- **Today's Performance**: Fixed the "Today's Done" count to use **Local Time** instead of UTC, so your progress shows up correctly.
- **Accuracy**: Now calculates correctly based on your study records.

### 3. Paper Detail Badges
- **Status Visibility**: The Paper Detail view now correctly displays:
    - 🔴 **Wrong**: Current active error.
    - 🟠 **History**: Past error.
    - 🟢 **Mastered**: Learned.
    - ⚠️ **Difficult**: Marked as difficult.

---

# Study Helper Pro V1.3.9 Walkthrough

## 🚀 V1.3.7 Update: Final Polish

This update delivers the strict isolation and comprehensive feedback you requested.

### 1. Strict Isolation
- **"All Loop" Fixed**: In Subject Study, "All Loop" now **strictly excludes** paper questions. It means "All Questions in this Subject's BANK".
- **Zero Leakage**: You can now study a subject without worrying about unlearned paper questions appearing.

### 2. Comprehensive Marking
- **Green "Mastered" Badge**: Added a green "Mastered" (已掌握) badge to the Paper Detail view. Now you see:
    - 🔴 **Wrong**: Currently wrong.
    - 🟠 **History**: Was wrong, now fixed.
    - 🟢 **Mastered**: Done and correct.
- **Study Feedback**: When you click "I did it right/wrong" in study mode, a toast message now explicitly confirms the action.

---

# Study Helper Pro V1.3.6 Walkthrough

## 🚀 V1.3.6 Update: Logic & Consistency

This update improves the accuracy of error tracking and study isolation.

### 1. Smart Error Tracking
- **Active vs History**: The "Wrong" count on Home and Subject pages now ONLY counts **Active Errors** (questions currently marked wrong).
- **Auto-Clear**: Answering a question *correctly* will now immediately remove the "Wrong" status and clear the Red Badge, giving you accurate real-time feedback.

### 2. Paper Detail Badges
- **Visual Status**: The Paper Detail view now shows status badges:
    - 🔴 **Red "Wrong X"**: You are currently getting this wrong.
    - 🟠 **Orange "History"**: You got this wrong before, but fixed it.

### 3. Strict Study Isolation
- **Bank Only**: "Start Study" on a Subject now strictly limits questions to the **Subject Bank**, excluding Paper questions (unless you explicitly choose "All Loop" or study a Paper directly).

---

# Study Helper Pro V1.3.5 Walkthrough

## 🚀 V1.3.5 Update: Missing Statistics

This update ensures that your error statistics are visible everywhere.

### 1. Home Page Statistics
- **Subject Cards**: Now display a **Red "X Wrong" Badge** next to the total count if you have any active or historical errors in that subject.

### 2. Subject Page Statistics
- **Stats Bar**: Added a new summary bar at the top of the subject page showing:
    - 📚 **Total**: Total questions in list.
    - ❌ **Wrong**: Count of questions with active errors OR historical errors.
    - ⭐ **Difficult**: Count of difficult questions.

---

# Study Helper Pro V1.3.4 Walkthrough

## 🚀 V1.3.4 Hotfix: Auto-Migration

This update fixes the "Subject List Error" by automatically repairing the database on startup.

### 1. Auto-Migration
- **Startup Check**: The server now checks if the `history_wrong` column exists.
- **Auto-Fix**: If missing, it automatically adds the column and backfills data from existing wrong answers.
- **Benefit**: No manual database commands required. Just `git pull` and restart.

---

# Study Helper Pro V1.3.3 Walkthrough

## 🚀 V1.3.3 Update: Persistent Error & Version Bump

This update ensures that "Exam Mistakes" (from Papers) are permanently marked, even if you study them correctly later.

### 1. Persistent Error Record
- **Database**: Added `history_wrong` tracking.
- **Behavior**:
    - When you mark a question as **Wrong** (in Paper or Bank), it gets a `Persistent Error` flag.
    - Even if you later practice it and get it **Right** (`wrong_count` resets to 0), the `Persistent Error` flag remains.
- **UI**:
    - **Active Error**: Red Badge "错 N 次" (Current proficiency is low).
    - **Past Error**: Orange Badge "曾错" (Current proficiency is high, but historically missed).
    - **List View**: The "Status" column now clearly shows if you ever missed the question.

### 2. Version
- Bumped to `V1.3.3`.

---

# Study Helper Pro V1.3.2 Walkthrough

## 🚀 V1.3.2 Update: Study Logic & UI Overhaul

This update fulfills the request for a more granular "Study Mode" selection and fixes the status recording issue.

### 1. New Study UI
- **Study Toolbar**: Added a toolbar in the Subject view with two dropdowns:
    - **Mode**:
        - `🔄 All Loop` (Entire Subject: Owned + Assigned Paper Questions)
        - `❌ Error Review` (Only Wrong Questions)
        - `⭐ Difficult Attack` (Only Difficult Questions)
        - `📚 Pure Bank` (Legacy: Only Manually Added Questions)
    - **Type**:
        - `📦 All Types`
        - `🔘 Single` / `☑️ Multi` / `📝 Fill` / `📑 Essay`
- **Start Study**: The button now launches the study session with the selected filters.

### 2. Logic Repair
- **Status Recording**: Fixed a bug where "Wrong/Difficult" status wasn't saving for Paper questions due to strict permission checks. Now, status can be recorded for any question you have access to.
- **Loop Logic**: "All Loop" mode now correctly includes ALL questions in the subject (both your own and assigned papers), ensuring a "Full Brush" experience.

---

# Study Helper Pro V1.3.1 Walkthrough

## 🚀 V1.3.1 Update: Study Logic Refinement & Admin Fixes

This update addresses user feedback regarding the visibility of paper questions and refines the study modes.

### 1. Admin Visibility Fix ("Pure Bank")
- **Issue**: Admins saw all paper questions in the "Subject" view because they technically owned the papers.
- **Fix**: The "Subject" view now strictly filters for `paper_id IS NULL`. This means even if you uploaded a paper, its raw questions won't clutter your bank view unless you explicitly clone them.

### 2. Error & Difficulty Visibility
- **V1.3.20**: Fix Type Display & Study Feedback
  - **Manage Page**: Updated "Type" column to show detailed types (Single, Multi, Fill, Big) instead of generic "Non-Select".
  - **Study Mode**: Added visual Toast feedback ("🎉 Marked Correct" / "Marked Wrong") when self-marking subjective questions.

- **V1.3.19**: Manage Page Sync & Badge Fix
  - **Visual**: Changed Subject Badge text from "难点" to "难" to prevent wrapping.
  - **Manage Page**: Fixed `manage_questions` query to correctly prioritize user's `is_difficult` status (aliasing fix). Added "Difficult" badge to Manage table.

- **V1.3.18**: Fix Priority of User Status
  - **Critical Fix**: Resolved "Marking Logic" issue where Subject List displayed legacy `wrong_count` instead of Active User Status (`uqs`).
  - **Implementation**: Used column aliasing and explicit overwrite pattern in `subject_detail` query (matching `paper_detail` logic).

- **V1.3.17**: Mark Logic Repair
  - **Logic**: Strictly aligned Subject Badges with Paper Center (font size 0.7rem, removed "次" suffix).
  - **Refinement**: Verified backend `record` API logic correctness.

- **V1.3.16**: Strict Scope & Sync Logic
  - **Scope**: Fixed `subject_page` and `study` route to STRICTLY exclude Paper questions (`paper_id IS NULL`). Previous V1.3.15 fix had loop-holes.
  - **Logic**: Synchronized Subject Badge Logic with Paper Center.
    - Added `has_record` detection.
    - Copied Badge Logic from `paper_detail.html`: Red (Wrong) > Orange (History) > Green (Mastered).
  - **Cleanup**: Removed duplicate code blocks and comments.

- **V1.3.15**: Logic Refinement & Scope Cleanup
  - **Scope**: Fixed Subject Page to exclude Paper questions (Initial Attempt).
  - **Logic**: Reverted Subject Badge Logic to match Paper Center (Orange/Red).
  - **Feature**: Added "Clear Difficult" button to `manage.html`.
  - **Cleanup**: Ensure "Delete Paper" cascades to delete its questions.

### 3. Refined Study Modes
The logical separation for "Start Studying" has been clarified:
- **Normal Mode**: **Pure Bank Only**. Questions you manually added or cloned. No raw paper questions.
- **Error Mode**: **All Errors**. Includes wrong questions from your Bank AND from assigned Papers.
- **Difficult Mode**: **All Difficult**. Includes difficult questions from your Bank AND from assigned Papers.

### 4. UI Changes
- **Subject Page**:
    - Added "Clone to Bank" button for transient paper questions.
    - Questions from papers are visible only if they need attention (Wrong/Difficult).

---

# Study Helper Pro V1.3.0 - 逻辑重构与专业化

## 🛠 本次更新重点 (V1.3.0)

### 1. 深度学习模式（逻辑重构）
- **难点标记持久化**：
    - 现在，做对题目 **不再自动移除** “难点/易错”标记。这是一项重大改进，旨在强调“做对不代表真正掌握”。
    - 难点消除必须在“题库管理”中 **手动确认** 移除，确保您真的不再需要复习它。
- **纯净题库**：
    - **隔离试卷错题**：做试卷时的错题不再自动污染您的“科目刷题”列表。
    - **主动收录制**：只有您在试卷界面**手动点击“克隆/加入题库”**的题目，才会进入您的专属刷题库。这保证了刷题库每一道题都是精华。

### 2. 界面与功能优化
- **科目列表修复**：
    - 彻底修复了学生端科目列表显示重复、出现“幽灵科目”（管理员分发的科目）的问题。现在的科目列表只显示您自己创建或拥有的科目。
- **手动移除难点**：
    - 在“题库管理”页面，对于且仅对于标记为“难点”的题目，新增了一个**橙色“移除难点”按钮**。点击即可手动清除其难点状态。

## 📦 部署指南
请在 NAS 的 `/vol2/1000/data/study-helper-pro/StudyHelper` 目录下执行：
```bash
git pull origin main
docker-compose up -d --build
```
更新后，请刷新浏览器缓存。
