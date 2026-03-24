# Technical Audit Report: Study Helper (SH)

## Executive Summary
The **Study Helper (SH)** project is a FastAPI-based web application for managing exam questions, paper slicing, and study tracking. While the UI is modern and the core functionality is clear, the system has **critical security vulnerabilities** and **architectural flaws** that pose risks to data integrity and privacy.

---

## 1. Security Analysis

### ⚠️ Critical: Complete Lack of Authentication
- **Finding**: There is no authentication mechanism (login, token, or IP filtering). 
- **Impact**: Any user with network access to port `7788` can:
    - View and download all exam data.
    - Export/Import data.
    - Trigger a "Nuclear Reset" to delete all data and files.
    - Perform a full system backup (potentially leaking the entire DB).

### ⚠️ High: Potential Path Traversal
- **Finding**: The `import_data` and `restore_backup` functions use `zipfile.extract` on uploaded files without validating if the internal paths contain `../`.
- **Impact**: A malicious zip file could overwrite sensitive system files or application code inside the container.

### ⚠️ Medium: Concurrency & Privacy Risk
- **Finding**: The `/api/slice-upload` endpoint uses a fixed temporary path `/tmp/study_helper/current_exam.pdf`.
- **Impact**: If two users upload PDFs simultaneously, they will overwrite each other. One user might end up seeing "slices" of another user's document.

---

## 2. Architecture & Code Quality

### Architectural Coupling
- **Finding**: Absolute paths like `/app/data/study.db` and `/app/static/uploads` are hardcoded in `main.py`.
- **Impact**: The code is not portable and strictly depends on the specific Docker volume configuration.

### Resource Management
- **Finding**: Database connections are opened and closed manually in almost every route.
- **Impact**: Increased risk of connection leaks and redundant code. FastAPI's dependency injection system (using `yield`) is the standard practice here.

### Error Handling
- **Finding**: Multiple instances of `except: pass` or `try...except` without logging.
- **Impact**: Silent failures make debugging difficult and can hide logic errors.

---

## 3. Recommendations

### Immediate Actions (Security)
1.  **Add Authentication**: Implement at least a basic password protection or API key check for all routes.
2.  **Sanitize Zip Extractions**: Ensure that zip entry filenames do not contain path traversal sequences before extraction.

### Structural Improvements
1.  **Environment Variables**: Move all hardcoded paths and port settings to environment variables.
2.  **Unique Temp Files**: Use `uuid` or `tempfile` modules for PDF processing to ensure multi-user safety.
3.  **Database Session Management**: Refactor `get_db` to be used as a FastAPI dependency to ensure consistent connection lifecycle.

---

## conclusion
The project is functional for private use, but it should **not** be exposed to any public or semi-public network in its current state.
