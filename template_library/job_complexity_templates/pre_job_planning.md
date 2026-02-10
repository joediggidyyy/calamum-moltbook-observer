# Pre-Job Planning Template (VAULT)

Purpose: For larger cross-team jobs. Break the job into separate 'Quests' with complexity scoring and time estimates.

Metadata

- Title:
- Owner(s):
- Stakeholders:
- Date:
- Expected Window / Sprint:

Estimator Inputs (for estimator):

- size: (e.g., 20 files / 100-1000 LOC)
- integration_points: (number)
- tests_needed: (#)
- docs_needed: (yes/no)
- approvals_needed: (#)
- risk: (0-10)

Quests (example)

1. Quest: Design & Architecture
   - Description: high level approach, API/contract design
   - Estimated Hours: 8
   - Complexity Score: 20

2. Quest: Core Implementation
   - Description: code changes, business logic
   - Estimated Hours: 24
   - Complexity Score: 40

3. Quest: Integration & Adapters
   - Description: integrate with services/systems
   - Estimated Hours: 12
   - Complexity Score: 20

4. Quest: Tests & CI
   - Description: unit/integration/tests
   - Estimated Hours: 10
   - Complexity Score: 10

Total Hours (sum): 54
Overall Complexity (estimator): XX / 100

Approval / Reviewers

- Primary Approver:
- Security Reviewer:
- Release SME:
- QA Lead:

Acceptance Criteria

- Clear, automated tests for essential workflows
- CI green for feature branches + all relevant integration checks
- Documentation complete and reviewed
