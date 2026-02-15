# Study Helper Pro V1.3.27 Walkthrough

## 🛠️ V1.3.27: Restoration of "Unmark Difficult"
**Release Date**: 2026-02-15

### 🐛 Fixed Issue
- **Missing Button**: The "Unmark Difficult" (去除难点) button was accidentally removed from the Question Bank Management interface. It has now been restored.

### 🌟 Usage
1. Go to **Question Bank Management** (题库管理).
2. Find any question marked with a red "Difficult" (难) badge.
3. You will now see a yellow star button <i class="fas fa-star-half-alt"></i> in the actions column.
4. Click it to remove the difficult status.

### 🔍 Verification
- Verified `manage.html` template logic to conditionally show the button only for difficult questions.
- Confirmed `unmark_difficult` API endpoint exists and is functional in `main.py`.
