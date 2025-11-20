# CWM (Command Watch Manager)

![Status](https://img.shields.io/badge/Status-Early%20Development-yellowgreen)
![Version](https://img.shields.io/badge/version-1.0.0-blue)
![License](https://img.shields.io/badge/License-MIT-green)

**Developer:** Developed by Vibe Coder

---

## (❁´◡`❁) Project Introduction

CWM is a command-line tool designed to bring powerful history, saving, and session management features to your terminal commands. It provides an intuitive way to manage your common and project-specific shell actions without complex external dependencies.

### What it does?
* Saves your commands that you run in the terminal, get them, and filter them.
* No backend or other sketchy processes.
* For documentation and codes, refer to the project's documentation.

### What in the future?
* Maybe something like a batch file to automate some processes in our own style.
* Directly execute the command without copying it.
* But it needs implementation of a background terminal (Active Shell Mode) in the future.

### If you want to contribute?
* Create a new branch, work there, and push it.
* Any bugs and logic faults can be reported.
* If you have any other ideas, you can say them.

### Is this project already present?
* Maybe, I don't know. You can get the history no sweat in both Linux and Windows.
* And I don't care, it's fun.

---

> [!WARNING]
> ### (●'◡'●) Important Notices & Limitations
>
> **1. Windows Command Prompt (`cmd.exe`) Limitation**
> * The standard Command Prompt does **not** save command history to a file. Therefore, `cwm get --hist` and `cwm watch` features **will not work** in `cmd.exe`.
> * **Recommendation:** Please use **PowerShell** or **Git Bash** on Windows.
>
> **2. Linux/WSL Users (`cwm setup`)**
> * By default, Bash/Zsh only saves history when you close the terminal. This causes a delay for CWM.
> * **Run `cwm setup` once** after installation. This command safely updates your `.bashrc` to sync history instantly, allowing CWM to work in real-time.

---

## ╰(*°▽°*)╯ Command Reference

### Initialization & Core
| Command | Action | Example |
| :--- | :--- | :--- |
| `cwm hello` | Displays welcome, version, and system info. | `cwm hello` |
| `cwm init` | Initializes a new **Local Bank** (`.cwm` folder). | `cwm init` |
| `cwm setup` | **(Linux/Mac/GitBash)** Configures shell for instant history sync. | `cwm setup` |
| `cwm config --shell` | Selects the preferred history file to read from. | `cwm config --shell` |
| `cwm config --stop-warning` | Disables the "large history file" warning. | `cwm config --stop-warning` |

---

### Saving Commands (`cwm save`)
Handles saving to local bank, caching history, and managing global archives.

| Flag / Payload | Description | Example |
| :--- | :--- | :--- |
| (none) | Saves a raw command or variable. | `cwm save my_cmd="ls -la"` |
| `-l` | Lists all saved commands (local bank). | `cwm save -l` |
| `-e <var=cmd>` | Edits the command string for an existing variable. | `cwm save -e my_cmd="ls -al"` |
| `-ev <old> <new>` | Renames an existing variable. | `cwm save -ev my_cmd new_cmd` |
| `-b <var>` | Saves the *last command* from live shell history. | `cwm save -b last_run` |
| `--hist -n` | Saves new commands from live history to CWM cache (`history.json`). | `cwm save --hist -n 5` |
| `--archive` | **Smart Archive:** Deduplicates live history and moves it to the Global Bank archives. | `cwm save --archive` |

---

### Retrieving Commands (`cwm get`)
Central command for reading. Automatically copies to clipboard unless `-s` is used.

| Flag / Argument | Mode | Description | Example |
| :--- | :--- | :--- | :--- |
| **(none)** | Saved | Defaults to listing saved commands (`-l`). | `cwm get` |
| `<name>` / `--id` | Saved | **Copies** a single command to clipboard. | `cwm get my_cmd` |
| `-s` | Saved | **Shows** the command without copying. | `cwm get my_cmd -s` |
| `-l` | Saved | Lists saved commands and prompts to copy. | `cwm get -l` |
| `-t <tag>` | Saved | Filters the list by tag. | `cwm get -t dev` |
| `--hist` | History | Lists **live** shell history and prompts to copy. | `cwm get --hist` |
| `--hist -a` | Active | Lists history **only** from the active watch session. | `cwm get --hist -a` |
| `--cached` | Cache | Reads from `history.json` cache instead of live history. | `cwm get --hist --cached` |
| `--arch` | Archive | Lists all global archives (or shows Latest if no ID). | `cwm get --arch` |
| `--arch <id>` | Archive | Lists commands from a specific archive ID. | `cwm get --arch 1` |
| `-n`, `-f`, `-ex` | Filter | Common filters (Count, Filter string, Exclude string). | `cwm get --hist -f "git"` |

---

### Context Packer (`cwm copy`)
Scans your project and packs code files into the clipboard for LLMs.

| Flag | Description | Example |
| :--- | :--- | :--- |
| (none) | Opens the interactive file tree. Select IDs to copy. | `cwm copy` |
| `--init` | Creates/Resets `.cwmignore` with defaults. | `cwm copy --init` |
| `<ids>` | Manual mode. Copies specific file/folder IDs (comma-separated). | `cwm copy 1,5,8` |
| `--tree` | Copies the visual file tree structure only. | `cwm copy --tree` |
| `--condense` | Minifies code (removes comments/whitespace) to save tokens. | `cwm copy 1,2 --condense` |
| `-f <filter>` | Filters the displayed tree. | `cwm copy -f "src"` |

---

### Watch Mode (`cwm watch`)
Session tracking without background processes.

| Command | Description |
| :--- | :--- |
| `cwm watch start` | Starts a session by marking the current history line. |
| `cwm watch status` | Shows if a session is **ACTIVE** and the start line. |
| `cwm watch stop` | Stops the session. |
| `cwm watch stop --save` | Stops and saves session commands to `history.json`. |

---

### Backup & Data (`cwm backup`, `cwm bank`, `cwm clear`)
Manage data integrity and locations.

| Command | Action | Description |
| :--- | :--- | :--- |
| `cwm backup list` | List | Lists backups for `saved_cmds.json`. |
| `cwm backup merge` | Merge | Interactive tool to merge backups (`-l`, `--chain`). |
| `cwm bank info` | Info | Shows Local and Global bank paths. |
| `cwm bank delete` | Delete | **(Danger)** Deletes a bank (`--local` or `--global`). |
| `cwm clear` | Clear | Bulk deletes commands from saved/history (`-n`, `-f`, `--all`). |

