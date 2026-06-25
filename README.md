# ctx

Lightweight terminal context and vault variable manager for Linux.

`ctx` stores named sets of shell variables (IP addresses, domains, credentials, tokens, hosts, ports, and more) and loads them into your current terminal on demand. It is built for pentesting labs, Hack The Box / Proving Grounds machines, client engagements, homelabs, and cloud or dev workflows where context switches are frequent.

## Why this exists

Pentesters and operators often juggle multiple targets at once. Exporting variables by hand is repetitive; keeping them in notes means copy-paste friction. `ctx` gives you persistent, per-context variable stores with a minimal workflow:

1. Create a vault (`ctx create`) and load it (`ctx load <vault>`).
2. Store or update variables (`ctx set`) — each successful set auto-reloads.
3. Use `$ip`, `$user`, `$pass`, and friends in normal commands.

Switching vaults with `ctx load <other>` unloads variables from the previous vault before loading the new one. Use `ctx unload` to clear loaded variables without deleting the vault file.

For CTFs, Hack The Box machines, long-running pentests, and client engagements, `ctx` lets you keep collected values such as IPs, domains, credentials, tokens, hosts, and ports in one reusable vault. If you pause the job, close the terminal, or accidentally lose the session, just load the vault again and continue with the same variables. When something changes, such as a new HTB machine IP, update only that value with `ctx set` and keep moving.


Because Python cannot export variables into a parent shell, `ctx` is implemented as a **shell function** wrapping a **Python backend** (`ctxctl`).

## Installation

From the project directory:

```bash
chmod +x install.sh uninstall.sh
./install.sh
```

The installer will:

- Install `ctxctl` via **pipx** (preferred) or `python3 -m pip --user`
- Install `ctx` and `ctxctl` to **`~/.local/bin`** (standard user-local programs directory)
- Add `~/.local/bin` to your **PATH** in `~/.bashrc` and `~/.zshrc`
- Configure **shell integration** automatically in those rc files
- Copy completions to `~/.local/share/ctx/completions/`
- Install the man page to `~/.local/share/man/man1/ctx.1`
- Create the vault directory (`$XDG_CONFIG_HOME/ctx/vaults/` if `XDG_CONFIG_HOME` is set, otherwise `~/.config/ctx/vaults/`) with permissions `700`

After install, open a **new terminal** or run `source ~/.zshrc` (or `~/.bashrc`). The `ctx` command will then be available.

## Shell setup

`install.sh` configures this automatically. It appends a marked block to `~/.bashrc` and `~/.zshrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
# sources ~/.local/share/ctx/shell/ctx.sh or ctx.zsh
```

After installing, activate it in your current terminal:

```bash
source ~/.zshrc    # zsh (Kali, ParrotOS)
source ~/.bashrc   # bash (Ubuntu)
```

Or open a new terminal window.

### Manual setup (optional)

If you prefer not to modify rc files automatically, add this yourself:

**Zsh** (`~/.zshrc`):

```bash
export PATH="$HOME/.local/bin:$PATH"
source ~/.local/share/ctx/shell/ctx.zsh
```

**Bash** (`~/.bashrc`):

```bash
export PATH="$HOME/.local/bin:$PATH"
source ~/.local/share/ctx/shell/ctx.sh
```

## Quick start

```bash
ctx create forest
ctx load forest
ctx set ip 10.10.10.161
ctx set domain forest.htb

echo $ip
nmap -sC -sV $ip
```

`ctx create` makes a new vault. `ctx load` only works on existing vaults (typos will not create stray vaults). `ctx set` auto-reloads into your shell.

## Terminal-local contexts

The active vault is **per terminal**, not global.

- Terminal 1: `ctx load forest`
- Terminal 2: `ctx load sauna`

Each session exports its own `CTX_ACTIVE_VAULT`. They do not interfere.

`ctx current` shows the vault for **this** terminal only. If none is selected, it prints a helpful message and exits non-zero.

## `ctx load`, `ctx unload`, and `ctx set`

| Command       | What it does |
|---------------|--------------|
| `ctx load <vault>` | Load an **existing** vault into this terminal. Unloads variables from the previously loaded vault, then applies the new one. Fails if the vault does not exist — use `ctx create` first. |
| `ctx load`    | Reload the **active** vault's variables from disk (no vault switch). Useful after `ctx edit`, `ctx unset`, or `ctx clear`. |
| `ctx unload`  | Remove all variables from the loaded vault from this shell session. Clears active/loaded state. Does not delete the vault file. |
| `ctx set`     | Writes a variable to the active vault, then **auto-reloads** the vault. Updated values are immediately available as `$key`. |

Typical flow: `ctx create` once, `ctx load <vault>`, `ctx set` as needed, `ctx unload` when done with a target.

## Command reference

| Command | Description |
|---------|-------------|
| `ctx create <vault>` | Create a new empty vault (does not load it) |
| `ctx load [<vault>]` | Load vault into shell; with name switches vault (shell integration) |
| `ctx unload` | Unload vault variables from this shell session (shell integration) |
| `ctx current` | Show active vault |
| `ctx list` | List all vaults |
| `ctx set <key> <value>` | Set variable in active vault; auto-reloads into shell (shell integration) |
| `ctx get <key>` | Print variable value |
| `ctx unset <key>` | Remove variable |
| `ctx show` | Show vault name and all variables |
| `ctx clear [--force]` | Clear all variables (prompts unless `--force`) |
| `ctx edit` | Edit vault in `$EDITOR` (nano/vi fallback) |
| `ctx path` | Print active vault file path |
| `ctx delete <vault> [--force]` | Delete vault (prompts unless `--force`) |
| `ctx rename <old> <new>` | Rename vault |
| `ctx duplicate <old> <new>` | Copy vault |
| `ctx help` / `ctx --help` | Show help |

Backend help: `ctxctl --help` and `ctxctl <command> --help`.

## Security model

- Vaults are **plaintext** env files at:
  - `$XDG_CONFIG_HOME/ctx/vaults/<name>.env` (when `XDG_CONFIG_HOME` is set)
  - otherwise `~/.config/ctx/vaults/<name>.env`
- The installer and uninstaller resolve this same path, honoring `XDG_CONFIG_HOME` (an unset or empty value falls back to `~/.config`).
- Permissions: the config dir and `vaults/` are `700`; vault files are `600`.
- **No encryption** in v1.
- Secrets are **not masked** in `ctx show` or `ctx get`.
- Validation **warns** on common keys (IP, port, URL, domain) but never blocks.
- Values are **single-line** only. A value containing a newline or carriage return is rejected, because the vault format is line-oriented `KEY=VALUE` storage. Values may freely contain spaces, quotes, semicolons, dollar signs, backticks, and parentheses — they are stored and re-emitted as quoted data, never executed.
- Do not commit vault files to git.

### Hardened loading

Vault files are user-editable, plaintext env-style files. **They are not sourced by your shell.**
When you run `ctx load` or `ctx set`, the Python backend parses the vault as data and the shell
integration evaluates only backend-generated `export` / `unset` statements with robust quoting.
This prevents arbitrary shell code in vault files from executing on load.

Loading is transactional from the shell's perspective: the backend-generated script is produced
first and only applied if generation succeeds. If a vault is malformed or contains an unsafe
variable name, `ctx load` fails with a clear error, returns non-zero, and leaves your previous
vault and its variables untouched — `CTX_ACTIVE_VAULT` is never pointed at a vault that failed to load.

Remember: exported variables are visible to child processes. Treat secrets accordingly.

## Examples

### HTB / pentesting

```bash
ctx create forest
ctx load forest
ctx set ip 10.10.10.161
ctx set domain forest.htb
ctx set user svc-alfresco
ctx set pass 'Password123!'

nmap -sC -sV $ip
evil-winrm -i $ip -u $user -p $pass
```

Switch to another target — previous vault variables are cleared automatically:

```bash
ctx load sauna
echo $ip    # empty; sauna vault is now loaded
```

### Homelab

```bash
ctx create proxmox
ctx load proxmox
ctx set host pve.lab.local
ctx set user root
ctx set pass 'your-password'

ssh $user@$host
```

### Cloud / dev

```bash
ctx create aws-staging
ctx load aws-staging
ctx set url https://api.staging.example.com
ctx set token eyJhbGciOiJIUzI1NiIs...

curl -s -H "Authorization: Bearer $token" "$url/health"
```

## Troubleshooting

**`ctx: command not found`**

Run `source ~/.zshrc` or open a new terminal after `./install.sh`. Verify binaries exist:

```bash
ls -l ~/.local/bin/ctx ~/.local/bin/ctxctl
echo $PATH | tr ':' '\n' | grep local/bin
```

**`ctx load` / `ctx unload` / `ctx set` fail from a subprocess**

These require the `ctx` shell function (not the `~/.local/bin/ctx` launcher alone). Ensure the install block is in your rc file and you have sourced it.

**`No active vault in this terminal`**

Run `ctx load <vault>` before `set`, `get`, etc.

**Unload when finished with a target**

`ctx unload` removes `$ip`, `$user`, and other loaded vault variables from the shell without deleting the vault file.

**Variables not updating after `ctx edit`, `ctx unset`, or `ctx clear`**

Run `ctx load` (no vault name) to refresh shell variables, or use `ctx set` (which auto-reloads). Calling `ctxctl` directly bypasses shell auto-load — use the `ctx` shell function instead.

**Stale variables after switching vaults**

`ctx load <other-vault>` unloads the previous vault before loading the new one. Re-source your shell integration if behavior seems wrong.

**Validation warnings**

Warnings go to stderr and do not block the command. Fix values if the warning is correct.

**Man page not found**

Ensure `~/.local/share/man` is in `MANPATH`, or run `man -l ~/.local/share/man/man1/ctx.1`.

## Development

```bash
python3 -m pip install -e ".[dev]"
python -m pytest
python -m compileall src
ruff check .
ruff format --check .
mypy
python -m build

# Shell checks (Linux; install zsh and shellcheck first)
bash -n install.sh uninstall.sh bin/ctx shell/ctx.sh completions/ctx.bash
zsh -n shell/ctx.zsh completions/ctx.zsh
shellcheck install.sh uninstall.sh bin/ctx shell/ctx.sh completions/ctx.bash
```

## Uninstall

```bash
./uninstall.sh
```

The uninstaller removes the install block from `~/.bashrc` and `~/.zshrc`, and asks before deleting vault data.

## License

MIT — see [LICENSE](LICENSE).
