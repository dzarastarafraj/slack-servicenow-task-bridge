# Slack Task Bridge — ServiceNow Zurich Runbook

> **Status: DESIGN / DOCUMENTATION ONLY — NOT DEPLOYED.**
>
> This repository is a new, independent ServiceNow project. The included `app.py` is a safe, nonfunctional scaffold and **does not yet implement the ServiceNow backend**. Do not deploy it for active Slack traffic or repoint the existing Slack Events URL or scheduler until the migration and acceptance tests are complete.
>
> The original working integration remains preserved in a separate, unchanged private repository.

## 1. Purpose

**Slack Task Bridge** is planned to link internal Slack channels to **ServiceNow Zurich** so teams can raise and discuss internal work without creating customer-facing CSM Cases.

**Primary design goals**

- A qualifying Slack root message creates one internal ServiceNow Task.
- The bridge replies with the Task number in the original Slack thread.
- Assignment, agent updates, and completion are reflected in Slack.
- Slack thread replies are saved as internal ServiceNow work notes.
- The bridge prevents duplicated tasks/messages and stops syncing once work is complete.
- The existing FastAPI/Vercel plus external cron polling architecture is retained.
- No separate database is required **if** reliable task/thread mapping and de-duplication can be stored securely in ServiceNow.

**Out of scope:** creating customer Cases (`sn_customerservice_case`), modifying live customer Case/IMS reporting, or publishing an app in ServiceNow Store.

## 2. Configuration placeholders

Replace these only when the target environment and task type have been approved. Never commit tokens, passwords, OAuth client secrets, or cron secrets.

| Placeholder | Meaning |
| --- | --- |
| `[COMPANY_NAME]` | Company or internal team |
| `[SLACK_WORKSPACE]` | Target Slack workspace |
| `[SLACK_APP_NAME]` | Target Slack application, e.g. Slack Task Bridge |
| `[SLACK_CHANNEL]` | An enabled private channel |
| `[GITHUB_REPOSITORY]` | Repository for this implementation |
| `[VERCEL_PROJECT]` | Separate Vercel project for this bridge |
| `[VERCEL_BASE_URL]` | HTTPS production URL of that project |
| `[SERVICENOW_INSTANCE_URL]` | Full HTTPS instance URL |
| `[SERVICENOW_TASK_TABLE]` | Approved concrete Task subtype table, NOT automatically `task` |
| `[ASSIGNMENT_GROUP_SYS_ID]` | Approved internal support group, if used |
| `[INTEGRATION_USER]` | Dedicated ServiceNow integration account |
| `[STATE_OPEN]` | Actual value of target task's open state |
| `[STATE_WAITING_INTERNAL]` | Actual value of waiting-for-requester state, if available |
| `[STATE_DONE_VALUES]` | Actual values that indicate completed/closed work |

**Open design decision:** confirm the task type in the Zurich instance. Candidates include a suitable existing task subtype or a dedicated internal support task. Do **not** create a generic Task record in the parent `task` table just because it exists. `sc_task` (Catalog Task) should only be selected if the Service Catalog lifecycle actually fits.

## 3. Planned end-to-end workflow

### 3.1 Slack root message → ServiceNow Task

- A new root message (not a thread reply) begins with `task:`.
- Retrieve the actual Slack channel name, user, and message text.
- Create a record in `[SERVICENOW_TASK_TABLE]`.
- Save a readable summary in the Task:
  - Short description: originating Slack channel / brief request.
  - Description: originating channel, sender, and request text.
  - Integration mapping: Slack channel ID, root message timestamp, thread timestamp, Slack sender ID, and bridge identity, in approved fields.
- Reply in the original Slack thread: `Task created: [TASK_NUMBER]`.
- Store the Task `sys_id` for subsequent API requests. The human-friendly number is for display.

**Trigger compatibility (planned):** retain the legacy `ticket:`, `:ticket:` and 🎫 triggers during migration if desired. They must all create the **same ServiceNow Task type**, not customer Cases. New preferred command is `task:`. A thread reply never creates a new task, even if it begins with a trigger.

### 3.2 Task assignment → Slack

When the ServiceNow task is assigned to a person or qualifying group, the poller adds 👀 to the original Slack root message. The reaction is added only once.

### 3.3 ServiceNow work note → Slack thread

When an agent adds an **internal work note** starting with `slk:` (alias `slack:`), the bridge:

1. Finds its original Slack thread from bridge metadata.
2. Posts only the command payload, not internal technical metadata.
3. Records a durable delivery marker so polling cannot post it twice.
4. Moves the task to `[STATE_WAITING_INTERNAL]` if this state is valid/configured.

Example note:

~~~text
slk: Can you confirm the issue is still happening?
~~~

Do not use customer-facing comments for internal Slack traffic.

### 3.4 Slack thread reply → ServiceNow work note

An ordinary reply to a mapped Slack thread is added to the same ServiceNow Task as a **work note**, with Slack sender identity and source timestamp. The task returns to `[STATE_OPEN]` if that is a valid transition. Replayed Slack events must not create duplicate notes.

Example stored note:

~~~text
Slack thread reply from [SLACK_DISPLAY_NAME]:
Here is the requested screenshot.

Bridge Slack reply saved: [SLACK_REPLY_TS]
~~~

### 3.5 Task completed → Slack and stop syncing

When the task reaches one of `[STATE_DONE_VALUES]`:

1. Add ✅ to the original Slack root message.
2. Post `Done` in the thread **once**.
3. Ignore further Slack replies and outbound `slk:` notes for that completed task.

Whether tasks can be reopened is a separate change request; **no automatic reopening** is assumed.

## 4. System architecture

~~~text
Slack private channel
  | root message / thread replies
  v
[VERCEL_BASE_URL]/api/slack/events
  | validate Slack signature + process event
  v
ServiceNow Zurich
  [SERVICENOW_TASK_TABLE]
  | Task fields / work notes / state / integration metadata
  ^
  | Table API (authorized integration user)
  |
[VERCEL_BASE_URL]/api/poll-servicenow   <-- PLANNED, not currently implemented
  ^
  | authenticated HTTP GET every 1 minute
  |
cron-job.org (separate job for ServiceNow bridge)
~~~

**No ServiceNow Store installation is required** for the external API approach.

### 4.1 ServiceNow API plan

Once `[SERVICENOW_TASK_TABLE]` has been selected, the standard Zurich Table API provides these general operations, subject to table ACLs:

| Operation | Proposed method / path |
| --- | --- |
| Create Task | `POST /api/now/table/[SERVICENOW_TASK_TABLE]` |
| Search Tasks | `GET /api/now/table/[SERVICENOW_TASK_TABLE]` |
| Retrieve Task | `GET /api/now/table/[SERVICENOW_TASK_TABLE]/[TASK_SYS_ID]` |
| Update Task / write work note | `PATCH /api/now/table/[SERVICENOW_TASK_TABLE]/[TASK_SYS_ID]` |

Work-note **reading** requires validation: ServiceNow work notes are journal entries, not an ordinary repeatedly readable text field. Test permitted access to journal entries (for example `sys_journal_field` with appropriate restrictions) or use an approved Scripted REST API. Do not assume Table API returns work-note history automatically.

Official documentation:

- [ServiceNow Zurich — Table API](https://www.servicenow.com/docs/r/zurich/api-reference/rest-apis/c_TableAPI.html)
- [ServiceNow Zurich — Journal fields](https://www.servicenow.com/docs/r/zurich/platform-administration/table-administration-and-data-management/r_JournalFields.html)
- [ServiceNow Zurich — REST API Explorer](https://www.servicenow.com/docs/r/zurich/api-reference/rest-api-explorer/explore-rest-api-for-table.html)

### 4.2 ServiceNow access prerequisites

Confirm all of the following before coding/deployment:

- The exact task subtype is available, licensable, and intended for internal work.
- `[INTEGRATION_USER]` can create, query, update, and assign that subtype using API access.
- The integration user can **write and read permitted work-note entries**.
- The subtype has a known state model, including a working equivalent of Open, Waiting Internal (if supported), and Done.
- Default assignment group and required fields are documented.
- Any mapping/marker fields are restricted to appropriate internal users.
- The application has permission to search recent tasks efficiently without scanning all company records.

## 5. Slack application

Use a **separate target Slack app or installation** as needed for `[SLACK_WORKSPACE]`; do not overwrite the existing production app's Event Request URL while testing.

- Slack Event Request URL (planned): `[VERCEL_BASE_URL]/api/slack/events`
- Bot event for private channel messages: `message.groups`
- Socket Mode: OFF for the HTTP Events API approach
- Bot scopes to validate in target workspace: `chat:write`, `groups:history`, `groups:read`, `reactions:read`, `reactions:write`, `users:read`
- Add the bot to each private Slack channel that should be integrated.

Validate Slack request signatures, retries, bot-origin events, and event idempotency. Do not process messages from channels where the bot is not authorized.

## 6. Vercel and cron-job.org

Create a **separate** `[VERCEL_PROJECT]` deployment. Do not replace the existing production deployment.

**Planned routes**

- `POST /api/slack/events`: receives Slack Events API messages.
- `GET /api/poll-servicenow`: polls assignments, new `slk:` work notes, and completion; this route **must be implemented**.
- A health-check route is optional.

**External scheduler**

- Job name: `[CRON_JOB_NAME]`
- URL: `[VERCEL_BASE_URL]/api/poll-servicenow`
- HTTP method: `GET`
- Desired cadence: once per minute, subject to ServiceNow rate limits and poller performance.
- Require a poller secret or equivalent authentication; a publicly callable endpoint must **not** be able to trigger unrestricted sync.
- Keep `vercel.json` compatible with the selected plan; use cron-job.org rather than assuming every-minute Vercel platform cron is available.

**Do not point cron-job.org at the existing live `/api/poll-helpdesk` endpoint.**

## 7. Environment variable plan

Variables below are the **proposed configuration contract**, not evidence that the current `app.py` supports them.

~~~dotenv
# Company context / deployment
COMPANY_NAME=[COMPANY_NAME]
VERCEL_BASE_URL=[VERCEL_BASE_URL]

# Slack (values in Vercel secrets, never in GitHub)
SLACK_BOT_TOKEN=[SLACK_BOT_TOKEN_SECRET]
SLACK_SIGNING_SECRET=[SLACK_SIGNING_SECRET_SECRET]

# ServiceNow
SERVICENOW_INSTANCE_URL=[SERVICENOW_INSTANCE_URL]
SERVICENOW_TASK_TABLE=[SERVICENOW_TASK_TABLE]
SERVICENOW_ASSIGNMENT_GROUP_SYS_ID=[ASSIGNMENT_GROUP_SYS_ID]

# Choose one supported integration authentication method in implementation:
# OAuth 2.0 is preferred where permitted by the instance policy.
SERVICENOW_AUTH_METHOD=[AUTH_METHOD]
SERVICENOW_CLIENT_ID=[OAUTH_CLIENT_ID]
SERVICENOW_CLIENT_SECRET=[OAUTH_CLIENT_SECRET]
SERVICENOW_INTEGRATION_USERNAME=[INTEGRATION_USER]

# Task state mapping: configure actual values, never borrow unrelated table IDs
SERVICENOW_STATE_OPEN=[STATE_OPEN]
SERVICENOW_STATE_WAITING_INTERNAL=[STATE_WAITING_INTERNAL]
SERVICENOW_STATE_DONE_VALUES=[STATE_DONE_VALUES]

# Scheduled poller protection
POLL_CRON_SECRET=[POLL_CRON_SECRET]
~~~

Authentication may require additional values (for example a refresh-token strategy or a dedicated service account), depending on the OAuth flow that ServiceNow admins approve. Add **only** the variables actually used by the implemented code.

Never store secret values in README files, screenshots, commits, Slack messages, or source-code constants. If a secret is exposed, rotate it.

## 8. No-database mapping and message de-duplication

The existing bridge stored Slack mapping in helpdesk ticket content. For ServiceNow:

**Proposed metadata** (subject to security/field approval):

~~~text
Bridge source: Slack Task Bridge
Slack Channel ID: [SLACK_CHANNEL_ID]
Slack Message TS: [SLACK_ROOT_MESSAGE_TS]
Slack Thread TS: [SLACK_THREAD_TS]
Slack User ID: [SLACK_USER_ID]
~~~

An approved, searchable mapping from `(channel_id, thread_ts)` to Task `sys_id` is required. Prefer restricted task fields or an approved integration metadata table; use Task description only if its visibility and query behavior are acceptable.

Also persist a marker for each processed inbound Slack event and each outbound ServiceNow journal entry. The poller must never replay a previously sent message after retries/restarts. If secure durable mapping cannot be implemented without extra storage, revisit the no-database constraint **before** production.

## 9. Test plan (all tests pending)

Perform these tests in a safe non-production environment using the selected task subtype, with real ACLs and states. Record actual results; don't mark them as passed merely because the old bridge worked.

| # | Test | Expected behavior |
| --- | --- | --- |
| 1 | Root message `task: Test request` | Exactly one ServiceNow Task created; Task number posted in original Slack thread |
| 2 | Ordinary root message | No Task created |
| 3 | Trigger text inside existing Slack thread | No new Task created |
| 4 | Duplicate Slack delivery/retry | No duplicate Task or work note |
| 5 | Agent assigned to Task | 👀 added to root Slack message once |
| 6 | ServiceNow work note `slk: Please confirm` | Message appears once in correct Slack thread; waiting state applied only if valid |
| 7 | Slack requester replies in original thread | Private Task work note added once; valid open transition performed |
| 8 | ServiceNow Task completed | ✅ reaction and `Done` exactly once |
| 9 | Either side sends message after completion | No further cross-system synchronization |
| 10 | Unmapped Slack thread | No unrelated Task modified |
| 11 | Missing/revoked API permissions | Safe error; no data leak or false success |
| 12 | Poller called without valid auth | Rejected with no work performed |

### Test log

~~~text
Environment: [TEST_ENVIRONMENT]
ServiceNow instance: [SERVICENOW_INSTANCE_URL]
Task table: [SERVICENOW_TASK_TABLE]
Tester: [TESTER]
Date: [TEST_DATE]
Passed: [NUMBER]
Failed: [NUMBER]
Open issues: [ISSUES]
~~~

## 10. Troubleshooting checklist

**Task not created**
- Verify `task:` appears at the **start of a root message**.
- Verify Slack app is installed in the target workspace and invited to the private channel.
- Verify Events subscription, request signature checks, Vercel logs, integration-user privileges, required Task fields, and target-table ACLs.

**Slack reply did not reach ServiceNow**
- Verify original thread mapping exists and Task is active.
- Check deduplication marker and ServiceNow work-note write permissions.
- Look for Slack event delivery failures in Vercel logs.

**ServiceNow `slk:` note did not reach Slack**
- Verify the note is in a supported **work_notes** journal field.
- Verify poller authentication, journal read privileges, polling cursor, and Slack channel permissions.

**Status does not change**
- Inspect actual state field and allowed transitions for `[SERVICENOW_TASK_TABLE]`.
- Do not assume any numeric state values from another ServiceNow table.

**Poller fails or posts duplicates**
- Inspect ServiceNow rate limits, time windows, processed-entry markers, retries, and Vercel function timeouts.
- Protect the endpoint from unauthenticated requests.

## 11. Files and migration steps

| File | Status in this branch |
| --- | --- |
| `README.md` | **Target ServiceNow design** (this document) |
| `app.py` | **Safe nonfunctional scaffold**; ServiceNow integration is not yet implemented |
| `requirements.txt` | Review after implementing ServiceNow requests |
| `pyproject.toml` | Review application name and runtime |
| `vercel.json` | Keep external cron; validate chosen Vercel plan |
| `livechat.config.json` | Not copied into this new repository; examine the old project only if needed |

**Migration sequence**

1. Confirm ServiceNow Task subtype, required fields, work-note access, and states.
2. Implement and locally test a ServiceNow client and secure metadata mapping.
3. Rewire Task creation, Slack reply → work note, and ServiceNow poller → Slack.
4. Implement signature checks, cron authentication, reliable idempotency, and error handling.
5. Create separate Slack/Vercel/cron resources and configure secrets.
6. Run every acceptance test in section 9.
7. Enable the new integration for one test channel and expand only after sign-off.

The source repository remains unchanged. **Do not repoint or redeploy the existing production Slack Bridge project to ship this new integration.**
