
---

### Task 0: [Task Name]
**prompt:**
1. I'm working on a program ChatGPT Clone with Streamlit + Hugging Face. [copy and paste assignment introduction]. [Development expectations]. once you understand this, I will give you further instructioins


2. API Setup [copy and paste] I've set up the token in secrets.toml and add it to .gitignore, help me complete the rest of the API requirements.

**AI Suggestion:** [updated app.py and requriements.txt]

**My Modifications & Reflections:** didn't see problems

---

### Task 1.A: Core Chat Application
**Prompt:** 
Now task 1: [copy and paste].
The task is divided into 4 parts. Now part A: [Part A: Page Setup & API Connection (20 points)]


**AI Suggestion:** [update app.py]
**My Modifications & Reflections:** first run, error. Ask codex to fix error for me.

---

### Task 1.B: Core Chat Application
**Prompt:** 
 Now part B: [Part B: Multi-Turn Conversation UI (30 points)]. After you complete this part, the expected UI should be like the one attached to this chat.

**AI Suggestion:** [update app.py] Replaced the hardcoded test message with real input via st.chat_input.
Rendered messages using st.chat_message and stored full history in st.session_state.
Sent the entire message history with each API request to preserve context.
Used a scrollable st.container(height=...) so the message history scrolls independently while the input bar stays fixed at the bottom.

**My Modifications & Reflections:** 
the model cannot remember my name from an earlier message: Added a system prompt to explicitly tell the model to remember and reuse user details from earlier turns, which usually fixes the “name memory” issue.

lost chat memory

---

### Task 1.C: Chat Management (25 points)
**Prompt:** "[Part C: Chat Management]"

**AI Suggestion:** [update app.py]

**My Modifications & Reflections:** good 

---

### Task 1.D: Chat Persistence (25 points)
**Prompt:** "[Part D: Chat Management]"

**AI Suggestion:** [update app.py]

**My Modifications & Reflections:** good 

---

### Task 2: Response Streaming (20 points)
**Prompt:** 
[copy and paste Task 2 descreption]

**AI Suggestion:** [update app.py]

**My Modifications & Reflections:** good

---

### Task 3: User Memory (20 points)
**Prompt:** [copy and paste descreption of task 3]

**AI Suggestion:** [update app.py]

**My Modifications & Reflections:** good

### Final modification (20 points)
**Prompt:** Check if the following Grading Rubric are fulfilled. [copy and paste Grading Rubric]

**AI Suggestion:** [update app.py]

**My Modifications & Reflections:** good
