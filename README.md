# CWM (Command Watch Manager)

![Status](https://img.shields.io/badge/Status-Active%20Development-yellowgreen)
![Version](https://img.shields.io/badge/version-1.1.0-blue)
![License](https://img.shields.io/badge/License-MIT-green)

**Developer:** Developed by Vibe Coder

---

## (❁´◡`❁) Project Introduction

CWM is a command-line tool designed to bring powerful history, saving, and session management features to your terminal commands. It provides an intuitive way to manage your common and project-specific shell actions without complex external dependencies.

### What it does?
* **Workspace Manager:** Auto-detects your projects and lets you "jump" to them instantly (opening VS Code, Terminals, etc.).
* **History Manager:** Saves your commands that you run in the terminal, filters them, and archives them.
* **Git Automation:** Handles SSH keys and automates the "Add -> Commit -> Push" workflow for new repos.
* No backend or other sketchy processes.

### What in the future?
* Global Search engine for commands (Local + Web).
* Service Orchestrator for microservices.

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
> * **Run `cwm setup` once** after installation. This command safely updates your `.bashrc` to sync history instantly.

---

## ╰(*°▽°*)╯ Command Reference

### (★) Workspace & Navigation (NEW)
Manage your coding projects and jump between them instantly.

| Command | Description | Example |
| :--- | :--- | :--- |
| `cwm project scan` | **Smart Scan:** Auto-detects projects in your Home folder. | `cwm project scan` |
| `cwm project add` | Manually adds the current folder as a project. | `cwm project add . -n my-api` |
| `cwm project remove` | Interactive cleanup. Sorts by "Least Used". | `cwm project remove` |
| `cwm jump` | Lists Top 10 most used projects to open. | `cwm jump` |
| `cwm jump <name>` | Opens the project in your Default Editor. | `cwm jump my-api` |
| `cwm jump <id> -t` | Opens a **New Terminal** window at the project path. | `cwm jump 1 -t` |
| `cwm jump 1,2`  | **Batch Jump:** Opens multiple projects. | `cwm jump 1,2 ` |

---

### Initialization & Configuration
| Command | Action | Example |
| :--- | :--- | :--- |
| `cwm hello` | Displays welcome, version, and system info. | `cwm hello` |
| `cwm init` | Initializes a new **Local Bank** (`.cwm` folder). | `cwm init` |
| `cwm setup` | **(Linux/Mac)** Configures shell for instant history sync. | `cwm setup` |
| `cwm config --editor`| Sets the editor for `cwm jump` (code, jupyter, etc). | `cwm config --editor "code"` |
| `cwm config --add-marker`| Adds a file marker for project detection. | `cwm config --add-marker "go.mod"` |
| `cwm config --shell` | Selects the preferred history file to read from. | `cwm config --shell` |

---

### (☁) Git Automation
Manage SSH keys and automate repository setup.

| Command | Description | Example |
| :--- | :--- | :--- |
| `cwm git add` | Wizard to generate SSH keys and add them to config. | `cwm git add` |
| `cwm git list` | Lists configured CWM accounts. | `cwm git list` |
| `cwm git setup` | Links folder to an account, fixes Remote URL, and **Automates Initial Push**. | `cwm git setup` |

---

### Saving Commands (`cwm save`)
Handles saving to local bank, caching history, and managing global archives.

| Flag / Payload | Description | Example |
| :--- | :--- | :--- |
| (none) | Saves a raw command or variable. | `cwm save my_cmd="ls -la"` |
| `-l` | Lists all saved commands (local bank). | `cwm save -l` |
| `-e <var=cmd>` | Edits the command string for an existing variable. | `cwm save -e my_cmd="ls -al"` |
| `-b <var>` | Saves the *last command* from live shell history. | `cwm save -b last_run` |
| `--hist -n` | Saves new commands from live history to CWM cache. | `cwm save --hist -n 5` |
| `--archive` | **Smart Archive:** Deduplicates live history and moves it to the Global Bank. | `cwm save --archive` |

---

### Retrieving Commands (`cwm get`)
Central command for reading. Automatically copies to clipboard unless `-s` is used.

| Flag / Argument | Mode | Description | Example |
| :--- | :--- | :--- | :--- |
| **(none)** | Saved | Defaults to listing saved commands (`-l`). | `cwm get` |
| `<name>` / `--id` | Saved | **Copies** a single command to clipboard. | `cwm get my_cmd` |
| `-s` | Saved | **Shows** the command without copying. | `cwm get my_cmd -s` |
| `--hist` | History | Lists **live** shell history and prompts to copy. | `cwm get --hist` |
| `--cached` | Cache | Reads from `history.json` cache instead of live history. | `cwm get --hist --cached` |
| `--arch` | Archive | Lists all global archives. | `cwm get --arch` |
| `-n`, `-f`, `-ex` | Filter | Common filters (Count, Filter string, Exclude string). | `cwm get --hist -f "git"` |

---

### Context Packer (`cwm copy`)
Scans your project and packs code files into the clipboard for LLMs.

| Flag | Description | Example |
| :--- | :--- | :--- |
| (none) | Opens the interactive file tree. Select IDs to copy. | `cwm copy` |
| `--init` | Creates/Resets `.cwmignore` with defaults. | `cwm copy --init` |
| `<ids>` | Manual mode. Copies specific file/folder IDs. | `cwm copy 1,5,8` |
| `--tree` | Copies the visual file tree structure only. | `cwm copy --tree` |
| `--condense` | Minifies code (removes comments/whitespace). | `cwm copy 1,2 --condense` |

---

### Watch Mode (`cwm watch`)
Session tracking without background processes.

| Command | Description |
| :--- | :--- |
| `cwm watch start` | Starts a session by marking the current history line. |
| `cwm watch stop --save` | Stops and saves session commands to `history.json`. |

---

### Backup & Data (`cwm backup`, `cwm bank`, `cwm clear`)
Manage data integrity and locations.

| Command | Action | Description |
| :--- | :--- | :--- |
| `cwm backup merge` | Merge | Interactive tool to merge backups (`-l`, `--chain`). |
| `cwm bank info` | Info | Shows Local and Global bank paths. |
| `cwm bank delete` | Delete | **(Danger)** Deletes a bank (`--local` or `--global`). |
| `cwm clear` | Clear | Bulk deletes commands (`-n`, `-f`, `--all`). |