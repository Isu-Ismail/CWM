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

## ╰(*°▽°*)╯Command Reference

### Initialization & Core
| Command | Action | Example |
| :--- | :--- | :--- |
| `cwm hello` | Displays welcome and current version. | `cwm hello` |
| `cwm init` | Initializes a new **Local Bank** (`.cwm` folder). | `cwm init` |
| `cwm setup` | **(Linux/Mac)** Configures shell for instant history sync. | `cwm setup` |

---

### Saving Commands (`cwm save`)
This dispatcher handles saving, editing, and history caching. All action flags are mutually exclusive.

| Flag / Payload | Description | Example |
| :--- | :--- | :--- |
| (none) | Saves a raw command or names a variable. | `cwm save my_cmd="ls -la"` |
| `-l` | Lists all saved commands (does not require a payload). | `cwm save -l` |
| `-e <var=cmd>` | Edits the command string for an existing variable. | `cwm save -e my_cmd="ls -al"` |
| `-ev <old> <new>` | Renames an existing variable. | `cwm save -ev my_cmd new_cmd` |
| `-b <var>` | Saves the last command from **live** shell history to a new variable. | `cwm save -b last_run` |
| `--hist -n` | Saves new commands from shell history to CWM cache (`history.json`). | `cwm save --hist -n 5` |

---

### Retrieving Commands (`cwm get`)
This is the central command for all "read" operations, capable of accessing saved commands, live history, or cached history.

| Flag / Argument | Mode | Description | Example |
| :--- | :--- | :--- | :--- |
| **(none)** | Saved (Fast) | Prints or lists the entire bank if no argument is given. | `cwm get` |
| `<var_name>` / `--id <id>` | Saved (Fast) | Prints a single saved command. | `cwm get my_cmd` |
| `-c` | Saved (Fast) | **Copies** the retrieved command to the clipboard. | `cwm get --id 5 -c` |
| `-l` | Saved (List) | Lists saved commands and prompts user to copy. | `cwm get -l` |
| `--hist` | History (Live) | Reads **live** shell history, lists, and prompts user to copy. | `cwm get --hist` |
| `--hist -a` | History (Active) | Reads history **only** since the last `cwm watch start`. | `cwm get --hist -a` |
| `--hist --cached` | History (Cache) | Reads history from the CWM cache (`history.json`). | `cwm get --hist --cached` |
| `-n <count>` | Filter | Shows the last N commands (e.g., `-n 5`). | `cwm get --hist -n 5` |
| `-f <filter>` | Filter | Filters commands containing the specified string. | `cwm get -l -f "deploy"` |

---

### Watch Mode (`cwm watch`)
Manages the state of a command session using the `watch_session.json` file.

| Command | Action | Behavior | Example |
| :--- | :--- | :--- | :--- |
| `cwm watch start` | Starts a session. | **Condition:** Must run after `cwm init`. Marks the current history line as the starting point. | `cwm watch start` |
| `cwm watch status` | Reports session state. | Shows if the session is **ACTIVE** or **INACTIVE**. | `cwm watch status` |
| `cwm watch stop` | Stops the session. | Stops tracking and resets the starting line to 0. | `cwm watch stop` |
| `cwm watch stop --save` | Stops and saves. | Stops tracking, reads all commands since `cwm watch start`, filters them, and saves them to the history cache. | `cwm watch stop --save` |

---

### Backup Management (`cwm backup`)
View and merge data versions interactively.

| Command | Action | Behavior | Example |
| :--- | :--- | :--- | :--- |
| `cwm backup list` | List all backups. | Shows unique ID, timestamp, and a command sneak peek. | `cwm backup list` |
| `cwm backup show -l` | List & Show | Lists backups and prompts user for a number to show content. | `cwm backup show -l` |
| `cwm backup show --latest` | Show Single | Shows the commands inside the newest backup file. | `cwm backup show --latest` |
| `cwm backup merge -l` | Merge (Single) | Lists backups and prompts user for a single number to merge. | `cwm backup merge -l` |
| `cwm backup merge --chain -l` | Merge (Chain) | Lists backups and prompts for a comma-separated list of numbers (e.g., `1,3,2`) to merge sequentially. **Aborts on invalid input.** | `cwm backup merge --chain -l` |

---

### Bank & Data Management
Manage your storage locations and clean up data.

| Command | Action | Description |
| :--- | :--- | :--- |
| `cwm bank info` | Info | Shows the location of your Active and Global banks. |
| `cwm bank delete` | Delete | **(Danger)** Permanently deletes a bank (`--local` or `--global`). |
| `cwm clear` | Clear | Clears commands from `saved_cmds.json` (`--saved`) or `history.json` (`--hist`). Requires `-n`, `-f`, or `--all`. |
