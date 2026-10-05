# Manazil — Codex Development Instructions

## 1. Project Overview

Manazil is a bilingual Arabic/English property rental platform focused on Sudan.

Technology stack:

- Flask
- PostgreSQL
- Docker / Docker Compose
- HTML / CSS / JavaScript
- Flask-Migrate / Alembic
- Azure production infrastructure

Arabic is the default language.

The application is developed locally using Docker and deployed to Azure.

---

## 2. Core Development Rules

Before implementing any feature, bug fix, or redesign:

1. Inspect the relevant existing code.
2. Understand the current routes, models, templates, services, tests, localization, and configuration.
3. Reuse existing functionality whenever possible.
4. Preserve existing working behavior unless the task explicitly requires changing it.
5. Do not rewrite working functionality unnecessarily.
6. Avoid unrelated refactoring.
7. Keep changes focused on the requested task.
8. Follow existing project architecture and coding patterns.

Prefer modifying the existing implementation over creating parallel or duplicate implementations.

---

## 3. Testing and Verification

Tests are part of every implementation.

After making changes:

- Run relevant automated tests first.
- Run the complete automated test suite when practical.
- Add or update tests for new behavior where appropriate.
- Do not weaken or delete valid tests simply to make a change pass.
- Investigate regressions before changing existing expectations.
- Use automated tests, CLI commands, HTTP requests, logs, database checks, and other non-browser verification when appropriate.

Report:

- tests executed
- pass/fail results
- unresolved failures
- anything requiring manual verification

### Browser Testing — Prohibited

Do NOT perform browser-based testing.

Do NOT:

- open the application in a browser
- launch a browser for verification
- use browser automation
- use Playwright
- use Selenium
- use Puppeteer
- use browser developer tools
- use browser emulators
- use debugger-attached browser inspection
- take browser screenshots
- perform visual browser inspection
- perform responsive testing through a browser
- attempt to inspect the application through a browser-based workflow

The user performs all browser, visual, responsive, and cross-browser testing manually.

For UI changes:

- implement the requested design
- inspect the HTML/templates/CSS/JavaScript
- use automated tests where appropriate
- verify responsive rules through code inspection
- report anything that requires manual visual verification

Do not treat the inability to perform browser testing as a blocker.

---

## 4. Arabic and English

Manazil is bilingual.

### Arabic

Arabic is the default language.

Arabic interfaces must:

- use RTL layout
- use natural Arabic alignment
- use appropriate Arabic wording
- preserve correct layout direction

### English

English interfaces must:

- use LTR layout
- provide equivalent functionality
- use the existing localization architecture

Do not create separate duplicated Arabic and English implementations when the existing localization system can be used.

All new user-facing text must support both languages.

Do not hard-code user-facing strings when the project localization mechanism should be used.

---

## 5. Responsive and Mobile-First Design

All public-facing interfaces must support:

- mobile
- tablet
- desktop

Mobile is a first-class experience, not simply a scaled-down desktop layout.

Avoid:

- horizontal scrolling
- clipped content
- fixed widths that break on smaller screens
- oversized components
- tiny touch targets
- desktop-only positioning

Use responsive layouts and existing project breakpoints/components where appropriate.

Responsive behavior should be implemented through HTML/CSS and verified through code inspection and automated tests where possible.

The user performs final responsive visual testing manually.

---

## 6. Design References

Design references are stored in:

    design-reference/

Examples include:

    mobile-homepage-reference.png
    property-posting-mobile-reference.png
    signin-design-reference.png

When a task identifies a design reference, inspect it and use it as the primary visual guide.

Reference images can define:

- layout direction
- visual hierarchy
- spacing
- component appearance
- responsive intent
- general visual style

Reference images do NOT override:

- application functionality
- security
- accessibility
- localization
- authorization
- data validation
- existing business rules

Do not modify files inside `design-reference/` unless explicitly instructed.

Do not serve production assets directly from `design-reference/`.

If an image or other asset from `design-reference/` is required by the application, copy it into the appropriate production static/assets directory and reference that copy.

The `design-reference/` directory should remain design documentation/reference material.

---

## 7. Manazil Visual Identity

Maintain a consistent Manazil visual language.

General direction:

- clean
- modern
- simple
- trustworthy
- property-focused
- mobile-friendly

Use Manazil green as the primary brand color.

Use red primarily for:

- errors
- destructive actions
- important warnings

Maintain consistency across:

- border radii
- spacing
- shadows
- typography
- buttons
- form controls
- cards
- navigation
- status indicators

Reuse existing design tokens, CSS variables, components, and patterns before introducing new ones.

Avoid unnecessary visual inconsistency between pages.

---

## 8. Authentication and Security

Do not weaken existing security for UI changes, testing convenience, or development speed.

Preserve existing:

- CSRF protection
- password hashing
- session security
- authentication checks
- authorization checks
- input validation
- safe redirects
- OAuth security
- production security configuration

Authentication UI changes should reuse existing backend authentication behavior whenever possible.

Do not duplicate authentication logic simply to implement a new design.

Never commit:

- passwords
- API keys
- OAuth secrets
- database credentials
- connection strings
- private tokens
- storage credentials

Use environment variables and the project's existing configuration patterns.

---

## 9. Database Changes

For database schema changes:

1. Update the appropriate model.
2. Create an Alembic/Flask-Migrate migration.
3. Add or update relevant tests.
4. Verify migration behavior using non-browser tools.

Do not manually modify production database schemas.

Do not destroy production data unless explicitly instructed.

Keep migrations backward-conscious where practical.

Do not edit old applied migrations unless there is a specific and justified reason.

Create a new migration instead.

---

## 10. Property Workflow

Respect the existing Manazil property lifecycle and authorization rules.

Do not bypass publication or moderation rules simply to make properties visible.

Preserve existing concepts such as:

- draft
- pending/review states where implemented
- published
- rented/unavailable
- archived

Before modifying property workflow behavior, inspect the existing models, routes, services, and tests.

Do not assume workflow behavior from design references.

Business rules in the application take precedence over visual mockups.

---

## 11. Property Photos and User Content

Preserve existing storage abstractions.

Do not assume local filesystem storage when production uses cloud/blob storage.

When working with uploads, preserve or implement appropriate:

- file type validation
- file size validation
- ownership checks
- access control
- error handling
- storage abstraction

Do not expose:

- storage credentials
- internal private paths
- private blob/container information
- secrets

Production and local storage behavior should remain compatible with the project's existing architecture.

---

## 12. Production Awareness

Manazil is deployed to Azure.

Development changes must not assume localhost-only behavior.

Be careful with:

- environment variables
- PostgreSQL
- Azure storage
- OAuth callback URLs
- HTTPS
- proxy headers
- containers
- migrations
- production configuration
- scaling behavior
- persistent vs ephemeral storage

Do not modify Azure infrastructure unless the task explicitly requires it.

Do not introduce development-only behavior into production configuration.

Preserve environment separation.

---

## 13. Docker

Manazil uses Docker/Docker Compose for local development.

Preserve existing container architecture unless a task specifically requires changing it.

When dependencies or application startup behavior changes:

- determine whether the image needs rebuilding
- verify Docker configuration
- keep development and production behavior compatible

Do not unnecessarily recreate infrastructure or containers when a simpler change is sufficient.

---

## 14. Dependencies

Avoid adding dependencies unless they provide clear value.

Before adding a dependency:

1. Check whether the project already provides the required functionality.
2. Prefer existing libraries and project patterns.
3. Prefer lightweight solutions.
4. Avoid introducing a large framework for a small feature.

Do not introduce a new frontend framework merely for UI changes.

Document significant new dependencies in the final report.

---

## 15. Code Quality

Prefer:

- simple implementations
- readable code
- small focused changes
- existing project patterns
- reusable components where useful
- clear naming
- maintainable CSS
- explicit business logic

Avoid:

- unnecessary abstractions
- duplicate logic
- large unrelated refactors
- premature optimization
- hard-coded environment-specific values
- parallel implementations of existing functionality

When a small change can solve the problem safely, prefer it over a large architectural rewrite.

---

## 16. Existing Functionality Takes Priority

A design change must not accidentally change business behavior.

For UI redesign tasks:

- preserve routes
- preserve form behavior
- preserve authentication
- preserve authorization
- preserve validation
- preserve database behavior
- preserve redirects
- preserve localization
- preserve security

If matching a design reference would require changing existing functionality, stop and identify the conflict rather than silently changing application behavior.

---

## 17. Before Completing a Task

Verify through code inspection and automated/non-browser testing:

1. The requested functionality is implemented.
2. Existing functionality remains intact.
3. Arabic support is preserved.
4. English support is preserved.
5. RTL/LTR implementation is correct in code.
6. Responsive/mobile CSS and templates are implemented.
7. Relevant automated tests pass.
8. Database migrations are correct when applicable.
9. Security behavior has not been weakened.
10. No secrets were introduced.
11. No unrelated functionality was changed.

Do NOT perform browser or visual testing.

The user is responsible for final:

- browser testing
- visual inspection
- responsive/mobile inspection
- cross-browser testing

---

## 18. Handling Problems

If implementation reveals an unexpected problem:

1. Investigate the root cause.
2. Do not apply a fragile workaround merely to finish the task.
3. Preserve existing working behavior.
4. Explain significant conflicts or risks.
5. Choose the smallest safe solution.

If a requested change conflicts with security, data integrity, or established business rules, identify the conflict before changing those rules.

---

## 19. Git and Scope Control

Keep changes scoped to the requested task.

Do not:

- modify unrelated files
- reformat large unrelated sections of the repository
- remove working code without reason
- change infrastructure unnecessarily
- commit secrets
- alter unrelated configuration

Do not create Git commits unless explicitly requested.

Before finishing, review the changed files and make sure they are relevant to the task.

---

## 20. Final Report

At the end of an implementation task, provide a concise report containing:

### Implemented
Briefly describe what was implemented.

### Files Changed
List the important files added or modified.

### Database
Mention migrations or database changes, if any.

### Tests
Report:

- tests executed
- number passed/failed
- unresolved failures, if any

### Manual Verification
List anything the user should verify manually in the browser, especially:

- visual appearance
- mobile layout
- responsive behavior
- cross-browser appearance

### Notes
Mention only important technical decisions, remaining issues, or required manual actions.

Keep the report concise when there are no significant issues.