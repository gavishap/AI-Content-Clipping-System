# Review Code Command

When the user says "/review" or asks to review code:

1. **Analyze the Code**
   - Check for type hint completeness
   - Verify error handling exists
   - Look for hardcoded values that should be config
   - Check for proper logging vs print statements
   - Verify docstrings exist

2. **Check Against Contracts**
   - Read `docs/ARCHITECTURE.md` for expected interfaces
   - Verify input/output types match the contract
   - Check that module is independently testable

3. **Security & Performance**
   - No hardcoded API keys
   - Async used for API calls
   - No N+1 patterns in loops
   - Memory-efficient for large files

4. **Report Findings**
   Format as:
   ```
   ## Code Review: <filename>
   
   ### ✅ Good
   - [list positive findings]
   
   ### ⚠️ Suggestions
   - [list improvements]
   
   ### ❌ Issues
   - [list problems that must be fixed]
   ```
