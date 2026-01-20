# Implement Task Command

When the user says "/implement-task" or asks to implement a specific task:

1. **Read Context**
   - Read `docs/TASKS.md` to find the task
   - Read `docs/ARCHITECTURE.md` for data flow context
   - Check if there's a specific task doc (e.g., `docs/TRANSCRIBER_TASK.md`)

2. **Plan Before Coding**
   - Identify which files need to be created/modified
   - List the functions/classes to implement
   - Note any dependencies or imports needed
   - Confirm the plan with the user before writing code

3. **Implement**
   - Create/modify files one at a time
   - Follow the rules in `.cursor/rules/python.mdc`
   - Use type hints, docstrings, and proper error handling
   - Write tests alongside the implementation

4. **Update Tracking**
   - Mark completed subtasks in `docs/TASKS.md`
   - Update `docs/STATUS.md` with session notes
   - Note any blockers or decisions made

5. **Verify**
   - Run tests: `pytest tests/test_<module>.py -v`
   - Run type check: `mypy src/<module>.py`
   - Report results to user

## Example Usage

User: "/implement-task transcriber"

Response:
1. Reading docs/TRANSCRIBER_TASK.md for detailed implementation guide...
2. Plan: Create src/transcriber.py with Transcriber class, Word dataclass, etc.
3. [Implement code]
4. [Update TASKS.md checkboxes]
5. Run tests and report results
