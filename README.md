# CWM (Command Watch Manager)

![Status](https://img.shields.io/badge/Status-Active%20Development-yellowgreen)
![Version](https://img.shields.io/badge/version-2.1.0-blue)
![License](https://img.shields.io/badge/License-MIT-green)

**Developer:** Developed by ISU

---

## (❁´◡`❁) Project Introduction

CWM is a terminal companion designed for developers who juggle multiple projects. It unifies workspace navigation, command history management, and background task orchestration into a single, intuitive CLI.

### What it does?
* **Workspace Manager:** Auto-detects your projects and lets you "jump" to them instantly (VS Code + Terminal).
* **Task Orchestrator:** Runs startup commands (servers, scripts) in the background or in new interactive windows.
* **Smart History:** Saves complex commands for reuse and filters your shell history.
* **Context Packer:** Prepares your codebase for LLMs (ChatGPT/Claude) by packing files into the clipboard.
* **Git Automation:** Manages multiple Git accounts (SSH keys) and automates repo setup.

---

> [!WARNING]
> ### (●'◡'●) Important Notices & Limitations
>
> **1. Windows Command Prompt (`cmd.exe`) Limitation**
> * `cmd.exe` does not save history to a file. Features like `cwm get --hist` will **not work**.
> * **Recommendation:** Use **PowerShell** (Windows) or **Git Bash**.
>
> **2. Linux/Mac Users (`cwm setup`)**
> * By default, Bash/Zsh only saves history on exit.
> * **Run `cwm setup` once** to enable real-time history syncing.

---

## ╰(*°▽°*)╯ Command Reference

### (★) Workspace & Navigation
Manage your coding projects and jump between them instantly.

| Command | Description | Example |
| :--- | :--- | :--- |
| `cwm project scan` | **Smart Scan:** Auto-detects projects in your Home folder. | `cwm project scan --root D:/Dev` |
| `cwm project add` | Manually adds the current folder as a project. | `cwm project add . -n my-api` |
| `cwm project remove` | Interactive cleanup wizard. | `cwm project remove` |
| `cwm jump` | Lists Top 10 most used projects to open. | `cwm jump` |
| `cwm jump <name>` | Opens project in Default Editor (VS Code/PyCharm). | `cwm jump my-api` |
| `cwm jump <id> -t` | Opens Editor **AND** a new Terminal window. | `cwm jump 1 -t` |

---

### (🚀) Task Orchestrator (NEW)
Define startup commands (e.g., `npm run dev`, `python main.py`) for your projects and run them easily.

| Command | Description | Example |
| :--- | :--- | :--- |
| `cwm run project` | Runs a project's startup command in the **background**. | `cwm run project my-api` |
| `cwm run project -x`| **Interactive Mode:** Launches command in a **New Window** (good for inputs). | `cwm run project -x` |
| `cwm group add` | Groups multiple projects together (e.g., Microservices). | `cwm group add backend` |
| `cwm run group` | Runs **ALL** projects in a group simultaneously. | `cwm run group backend` |
| `cwm run list` | Shows active background services/PIDs. | `cwm run list` |
| `cwm run stop` | Stops specific or all background services. | `cwm run stop --all` |

---

### (💾) Saved Commands & History
Save complex commands or retrieve past actions.

#### 1. Saving (`cwm save`)
| Flag / Payload | Description | Example |
| :--- | :--- | :--- |
| `key="val"` | Saves a command with an alias. | `cwm save build="npm run build"` |
| `-b <var>` | **Back Capture:** Saves the *last run command* from history. | `cwm save -b deploy_fix` |
| `-e <var=new>` | Edits an existing saved command. | `cwm save -e build="npm run prod"` |

#### 2. Retrieving (`cwm get`)
| Flag | Description | Example |
| :--- | :--- | :--- |
| (none) | Lists all saved commands (Interactive Copy). | `cwm get` |
| `<name>` / `--id` | **Copies** a specific command to clipboard. | `cwm get build` |
| `-s` | **Shows** the command value without copying. | `cwm get build -s` |
| `--hist` | Search **System Shell** history. | `cwm get --hist -f "git commit"` |
| `--active` (`-a`) | Search **Local Project** history (requires Watch Mode). | `cwm get -a` |

---

### (👀) Watch Mode
Automatically records commands executed inside a specific project into a local `project_history.txt` file.

| Command | Description |
| :--- | :--- |
| `cwm watch start` | Injects a shell hook to record commands locally. (Requires terminal restart/reload). |
| `cwm watch status` | Shows current watch session status. |
| `cwm watch stop` | Stops recording and removes the shell hook. |

---

### (🤖) AI Context Packer (`cwm copy`)
Scans your project and copies code to clipboard, optimized for LLMs.

| Flag | Description | Example |
| :--- | :--- | :--- |
| (none) | Opens the interactive file tree selector. | `cwm copy` |
| `--init` | Creates default `.cwmignore` file. | `cwm copy --init` |
| `--tree` | Copies only the file structure tree. | `cwm copy --tree` |
| `--condense` | Minifies code (removes comments/whitespace). | `cwm copy 1,2 --condense` |

---

### (☁) Git Automation
Manage SSH keys and automate repository setup.

| Command | Description |
| :--- | :--- |
| `cwm git add` | Wizard to generate SSH keys and add them to SSH config. |
| `cwm git setup` | Links folder to an account, fixes Remote URL, and **Automates Initial Push**. |

---

### Configuration & Maintenance

| Command | Action | Description |
| :--- | :--- | :--- |
| `cwm config` | **Wizard** | Interactive setup for Editor, AI Keys, and Shell. |
| `cwm config --clear-config`| **Reset** | Wipes all global configurations. |
| `cwm bank info` | **Info** | Shows path to Global and Local banks. |
| `cwm bank delete` | **Delete** | Deletes the `.cwm` folder (Global or Local). |
| `cwm clear --saved` | **Wizard** | Interactive deletion of saved commands. |
| `cwm clear --sys-hist` | **Clean** | Deduplicates and cleans system shell history. |