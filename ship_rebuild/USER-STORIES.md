# USER-STORIES.md — Ship App User Stories

## Authentication

- **US-AUTH-1:** As a user, I can log in with email and password so that I can access my workspace.
- **US-AUTH-2:** As a user, I can log out so that my session is terminated.
- **US-AUTH-3:** As a user, I am redirected to login if my session has expired.
- **US-AUTH-4:** As a user, I see my name and avatar in the sidebar when logged in.

## Dashboard

- **US-DASH-1:** As a user, I see issues assigned to me in the current sprint when I open the dashboard.
- **US-DASH-2:** As a user, I can click an issue on my dashboard to navigate to the issue detail view.

## Wiki

- **US-WIKI-1:** As a user, I can view a list of all wiki documents.
- **US-WIKI-2:** As a user, I can create a new wiki document with a title and body.
- **US-WIKI-3:** As a user, I can click a wiki to view its full content and metadata (creator, dates, maintainer).
- **US-WIKI-4:** As a user, I can edit a wiki document's title and body.
- **US-WIKI-5:** As a user, I can delete a wiki document (soft delete).

## Programs

- **US-PROG-1:** As a user, I can view a list of all programs with owner and project count.
- **US-PROG-2:** As a user, I can create a new program with title, body, and owner.
- **US-PROG-3:** As a user, I can click a program to view its overview (body, owner, approver, dates).
- **US-PROG-4:** As a user, I can switch to the "Issues" tab to see all issues across the program's projects.
- **US-PROG-5:** As a user, I can switch to the "Projects" tab to see all projects in the program.
- **US-PROG-6:** As a user, I can switch to the "Weeks" tab to see sprint plans across the program.
- **US-PROG-7:** As a user, I can edit a program's title, body, and RACI fields.
- **US-PROG-8:** As a user, I can delete a program (soft delete).

## Projects

- **US-PROJ-1:** As a user, I can view a list of all projects with owner, issue count, ICE score, and program.
- **US-PROJ-2:** As a user, I can create a new project with title, body, owner, and program association.
- **US-PROJ-3:** As a user, I can click a project to view its overview (body, ICE scores, owner, program link).
- **US-PROJ-4:** As a user, I can switch to the "Issues" tab to see all issues in the project.
- **US-PROJ-5:** As a user, I can switch to the "Weeks" tab to see issues grouped by week number.
- **US-PROJ-6:** As a user, I can edit a project's title, body, ICE scores, and RACI fields.
- **US-PROJ-7:** As a user, I can delete a project (soft delete).
- **US-PROJ-8:** As a user, I see the ICE score auto-calculated when I change impact/confidence/ease.

## Issues

- **US-ISS-1:** As a user, I can create a new issue with title, body, status, priority, assignee, project, and week.
- **US-ISS-2:** As a user, I can view an issue's full content with metadata sidebar (status, priority, assignee, estimate, week, project, program, dates).
- **US-ISS-3:** As a user, I can change an issue's status via dropdown on the issue view.
- **US-ISS-4:** As a user, I can change an issue's priority via dropdown.
- **US-ISS-5:** As a user, I can reassign an issue to a different user.
- **US-ISS-6:** As a user, I can assign an issue to a week/sprint.
- **US-ISS-7:** As a user, I can edit an issue's title and body.
- **US-ISS-8:** As a user, I can delete an issue (soft delete).

## Weeks

- **US-WEEK-1:** As a user, I can view the weeks tab in a project and see issues grouped by week number.
- **US-WEEK-2:** As a user, I see "Current" label on the latest week with assigned issues.
- **US-WEEK-3:** As a user, when I assign an issue to a week number, it appears in that project's weeks view.

## Navigation

- **US-NAV-1:** As a user, I can navigate between sections using the sidebar.
- **US-NAV-2:** As a user, clicking a row in any list view navigates to the detail page.
- **US-NAV-3:** As a user, the active sidebar link is visually highlighted.
- **US-NAV-4:** As a user, I can navigate from program → project → issue through drill-down.

## Teams

- **US-TEAM-1:** As a user, I can view a list of team members with name, email, and role.
