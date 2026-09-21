# PC Assistant, projects and spreadsheets (v0.6)

## Workspaces

Projects are general workspaces, not just Git repositories. Create one in
**Projects**, add instructions, link local folders and add reference documents.
**Use selected project** opens a new conversation in that workspace. Conversation
history is filtered to the active project. **Leave project** returns to personal
conversations. Existing v0.2 conversations remain personal.

Linked folders remain in place; unlinking does not delete source files. Added
reference documents store extracted text locally. Refreshing the folder index
lists at most 1000 supported files, inspecting at most 10,000 directory entries.
Build/dependency directories, known credential folders and symlinks are excluded.
When chatting in a project, bounded lookup reads up to 40 candidate files and
selects at most three references. PDF/workbook files are automatically considered
only if the question matches their filename; explicitly attach them for other
questions. This is keyword retrieval, not a complete semantic search of every file.

Project instructions and selected reference excerpts are sent to the phone model.
Original linked files are not uploaded to a cloud service. Project metadata lives
in `~/.local/share/jiezhi/projects` (or the XDG data location).

## Project chat actions

Project chat uses the guarded tool loop directly. Ask for a deliverable, then
review the proposed creation/edit diff; the host writes approved files to the PC.
A project without linked folders gets its own folder under
`~/Documents/JieZhi Projects/<name>-<id>`. Its path, an **Open folder** button and
an access-mode selector appear above chat. Existing linked folders are used in
place. Global PC Assistant folders do not extend project-chat file access.

New UTF-8 files and subfolders can be created. Existing files require inspection
before editing. Creation never overwrites an existing file, including a file
created by another program while approval was pending. File writes remain limited
to 64 KiB; binary document authoring requires separately reviewed commands.
Saved paths and action decisions appear in the conversation and persist in history.
Rollback can remove an unchanged assistant-created file or restore an edited file.
Folder creation has no automatic rollback.

Project chat prepares the currently selected model with an 8192-token context
when necessary; it does not select a different model. Each task is limited to
12 steps. Small-model tool reliability still depends on the model. Generated code
is only verified when an approved verification command succeeds.

## Spreadsheets

Attach `.xlsx`, `.xlsm`, `.xls`, `.ods`, `.csv` and `.tsv` in chat or as project
references. Excel/ODS extraction keeps sheet names and cell/row coordinates.
XLSX/XLSM/ODS formulas are exposed as text with cached values when available;
legacy XLS uses stored values. JieZhi does not recalculate formulas or execute
macros. Cached values may be stale. This release reads spreadsheet content; it
does not provide a spreadsheet editor or guarantee exact arithmetic from the LLM.

Limits: 20 MiB input; 64 MiB uncompressed XML for zipped formats; 30 sheets;
10,000 rows and 100 columns per sheet; 200,000 extracted characters. Password-
protected workbooks must be exported unlocked. Visible truncation markers apply.

## PC awareness

**PC Assistant** can gather OS/kernel/architecture, CPU-thread and memory data,
disk space, installed desktop-app launch entries, process names/resource use,
recent user journal entries and Debian package status. File reads are limited to
folders selected in Assistant or linked in the active project, plus installed
`.desktop` entries. It discovers evidence on demand; it has no omniscient or
permanent view of all PC state. It does not take screenshots or monitor user input.

Logs and configuration may contain private information. Common bearer tokens,
Hugging Face tokens and password/API-key assignments are redacted before tool
results reach the model. Redaction is best-effort, not a guarantee that arbitrary
logs contain no secrets. Known credential directories, `.env*`, private-key files,
JieZhi's own state, symlinks and hard-linked files are excluded from file tools.

## Access modes

The default is **Ask before changes**, as selected by the user.

| Mode | Diagnostics and scoped reads | File creation and edits | Commands |
| --- | --- | --- | --- |
| Read-only | Automatic | Blocked | Blocked |
| Ask before changes | Automatic | Approve each diff | Approve each command |
| Scoped autonomy | Automatic | Automatic within selected folders; startup files still ask | Approve each command |

The host enforces these rules regardless of what the model requests. The model
cannot grant itself folders, change modes or approve actions. Mode/folder scope
is frozen for the duration of an investigation. Rejecting an action stops the run.

File edits require an earlier read, an exact unique replacement and a matching
SHA-256 at execution time. The host attaches the observed hash, rechecks it after
approval, stores a private backup, and replaces the file atomically. The tools
limit direct reads/edits to 64 KiB UTF-8 regular files owned by the user for edits.

**Commands are not sandboxed to selected folders.** Approval covers the exact
argv, working directory, requested privilege and displayed risk. Commands can act
with the user's OS permissions, access the network and modify other files. There
is no automatic rollback of command effects. No shell is implicitly inserted;
an explicitly requested shell/interpreter remains visible in the argv. Ordinary
commands use Linux `setpriv --no-new-privs` where available. Administrator requests
are disabled initially, require a separate checkbox and approval per command,
and use `pkexec` with the desktop's normal authentication. No password is stored.
Administrator enablement is not persisted across launches.

**Stop** cancels future steps, dismisses pending approval and asks the phone to
stop generating. Running command groups are terminated on cancellation, timeout
or excessive output. Cancellation cannot undo side effects already performed,
and elevated descendants may require OS-level intervention if they outlive the
unprivileged launcher. Commands have a 90-second limit; diagnostic commands 20
seconds. Investigations stop after 12 model/tool steps. Invalid tool output never
executes as shell text.

## Review and recovery

The visible action log records proposed changes, approval/denial, tool output and
model conclusions. **Previous investigations** reopens saved local logs.
**Restore a file edit** presents a rollback diff and always asks for approval.
Rollback checks that the file still matches the assistant's last write; it refuses
to overwrite newer changes. Read-only mode also blocks rollback writes.

Logs/backups live in `~/.local/share/jiezhi/assistant` with user-only file modes.
Backups contain the original file contents and remain until removed by the user.
Uninstalling the app retains this data. A model conclusion is not proof of success;
the host reports command exit status and the log contains the actual evidence.

## Model requirements and limits

Load a compatible instruction model with at least 4096 context tokens; 8192 leaves
more room for diagnostic evidence. Small chat models may invent tools, choose
incorrect fixes or misread logs. This is a guarded prototype, not a guarantee of
repairing arbitrary software. Check every proposed command/diff, particularly
before enabling scoped autonomy or administrator requests. Native NPU inference
continues to run on the phone; the PC executes the approved diagnostic/repair tools.
