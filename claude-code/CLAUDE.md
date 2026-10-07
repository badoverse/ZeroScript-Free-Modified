# Roblox Studio workspace

This workspace connects you to the Roblox Studio place open on this machine through Studio's built-in MCP server, `roblox`. ZeroScript's `launch_studio_mcp.py` starts it on Windows, on macOS, and on Linux, where Studio runs under Vinegar's Wine.

Make changes in Studio yourself with the `roblox` tools instead of handing me code to paste. Show code only when I ask to see it; otherwise run it and tell me what happened.

## When the tools are missing or Studio is offline

- The tools appear only while Studio is open with a place loaded and *Assistant AI → … → Manage MCP Servers → Enable Studio as MCP Server* is on. Studio updates can switch that toggle back off. If the tools are missing, ask me to check, then reconnect `roblox` from `/mcp`.
- ZeroScript's own bridge also starts a StudioMCP; it should be closed while we work here.

## Reading Studio MCP results

The server reports several failures as ordinary, successful results. Treat these as errors:

- Text containing "Unable to find an active Studio instance" or "previously active Studio has disconnected" means Studio isn't connected. It's an environment problem, not a mistake in the call: tell me in one sentence and wait. Disconnects are usually brief, so when I say it's back, or before you tell me it's still down, run a tool again and let the fresh result decide.
- A result that is only "<parameter> is required", "… is not available" or "… is invalid" is a failed call. Fix the arguments and retry.
- An `execute_luau` result with internal frames such as `ExecuteLuauTool:139:` or `CommandExecution:54:` is a Luau error, not output. The real message is the last segment after the final `:`. For example, "Vector3 expected, got string", or "Failed to parse command code" for a syntax error.

## Working in the place

- **`datamodel_type`:** use `"Edit"` for changes that should last. `"Server"` and `"Client"` exist only while the game is playing, and `"Edit"` fails then with "Edit datamodel is not available in Play mode". Changes made in Play vanish when it stops: fine for checking live state, wrong for anything I want to keep. The player-input tools always take `"Client"`.
- **Build first, then script:** build UI and objects first with `execute_luau`, then write the Script or LocalScript that finds them with `WaitForChild(name, timeout)`. Create instances at runtime only when they're truly dynamic, such as per-player elements or lists of unknown length.
- **Geometry:** for objects with real geometry (a mesh, a prop, a procedural shape), prefer `generate_mesh` or `generate_procedural_model`. Build from parts with `execute_luau` only for simple shapes and positioning.
- **Deleting:**
  - Remove exactly what I named.
  - Before `:Destroy()`, `:ClearAllChildren()` or removing a script, check the target with `inspect_instance` if there's any doubt about what it contains.
  - If a deletion could reach beyond the thing I named (clearing a container, matching by a broad name, a whole model or service), ask me to confirm the scope first.
  - Don't delete things as a troubleshooting step without asking.
- **Property errors:** on a property, attribute or enum error, look up the valid values (`inspect_instance`, the Roblox API reference) before retrying, rather than guessing again.
- **Scope:** do what was asked with the fewest calls, and skip double-checks I didn't ask for.

## Tool notes

These were tested against a live Studio for ZeroScript (`TOOL_NOTES` in `zeroscript-extension/core/config.js`).

**execute_luau**
- Use `return` for output; `print()` isn't captured. Only the first returned value is shown, so return one table (`return {ok = true, n = 3}`). Tables come back as JSON.
- It runs synchronously on a budget of about 20 seconds. A short `task.wait(1)` is fine, but anything that can block will time out.
- Always pass a timeout to `WaitForChild`: `obj:WaitForChild("X", 5)`. Without one it blocks until the budget kills the whole call.
- Put event `:Wait()`s, endless loops, HttpService and DataStore calls in a real Script instead.
- Property types must match exactly (`Vector3.new(...)`, not a string). Create objects with `Instance.new` and set `.Parent`. Reach services with `game:GetService("Name")`.

**multi_edit**
- `old_string` must match the script's current text byte for byte, including tabs and spaces. Call `script_read` first and copy from it.
- Don't retype code that contains quotes or dashes: straight quotes can turn into curly ones and `--` into a long dash, which then won't match. `new_string` may contain any Unicode.
- It replaces only the first match and doesn't warn about others. A short `old_string` can silently edit the wrong line, so include whole lines for a unique match, or set `replace_all: true` for renames.
- `old_string` and `new_string` must differ. Edits apply in order, each on the result of the previous one, and are atomic: all succeed or none do.
- To create a script, set `className` (`Script`, `LocalScript` or `ModuleScript`) and make the first edit `old_string: ""` with the full source. `datamodel_type` must be `"Edit"`.

**script_read**
Reads the whole script with line numbers. `target_file` is a full dot path. It never creates a script; search for the path first.

**inspect_instance**
- The path is dot notation and case-insensitive, for example `Workspace.Model.Part`.
- It returns properties, attributes and a summary of children; inspect children separately. You get up to 20 matches when several instances share a path.
- Use it to read exact property names and values before editing them.

**generate_mesh / generate_procedural_model**
- `generate_mesh` blocks until the mesh is finished and returns it.
- `generate_procedural_model` returns a `generationId` immediately and inserts the model into the workspace when it's done, so don't assume the model exists yet.
- Call `wait_job_finished` with that id when your next step needs the finished model, or when I ask you to wait. Don't call it as a reflex.

**user_keyboard_input / user_mouse_input**
- These simulate a player, so they need `"datamodel_type": "Client"` and a running game. Call `start_stop_play` with `{"is_start": true}` first.
- `actions` is an ordered array of objects, each with an `"action"` key, never bare strings.
- **Keyboard actions:** `keyDown`, `keyUp`, `keyPress` (down then up), `textInput`, `wait`.
  - Key actions require `key_code`, which takes Roblox KeyCode names: `"Return"`, `"Zero"` to `"Nine"`, `"A"` to `"Z"`, `"Space"`, `"Backspace"`, `"Tab"`, `"Up"`/`"Down"`/`"Left"`/`"Right"`, `"LeftShift"`/`"LeftControl"`/`"LeftAlt"`.
  - To type a whole string, use one `textInput` step with `"text_inputs": "hello"`.
- **Mouse actions:** `moveTo`, `mouseButtonDown`, `mouseButtonUp`, `mouseButtonClick`, `scrollUp`, `scrollDown`, `wait`.
  - The first step needs `"x"`/`"y"` in screen pixels, or an `"instance_path"`. Later steps reuse the last position.
  - Clicks need `"mouse_button": "left"` or `"right"`.
- A `wait` step needs `"wait_time_ms"` (0 to 10000).
- An optional `"instance_path"` must start with `game`, `LocalPlayer` or `Workspace`, for example `LocalPlayer.PlayerGui.Menu.PlayBtn`.
- Example: `{"datamodel_type": "Client", "actions": [{"action": "textInput", "text_inputs": "hi"}, {"action": "keyPress", "key_code": "Return"}]}`

## Project memory

`game.ServerStorage.ZeroScript.Memory` is a ModuleScript that holds long-term notes about this project inside the place. ZeroScript sessions on other AIs read and write the same module, so keep it accurate for whoever reads it next.

- **When to read it:** the first time a request needs you to change the place or understand how the game works. Not for chit-chat or unrelated questions.
- **Creating it:** if it doesn't exist, create it with `multi_edit` (`className: "ModuleScript"`, first edit `old_string: ""`; the `ZeroScript` folder is created for you) using this skeleton:
  ```lua
  return [==[
  # Project memory
  ## Overview
  ## Where things live
  ## Conventions
  ## Key systems
  ## Decisions & gotchas
  ## User preferences
  ## Open questions / TODO
  ]==]
  ```
- **What to store:** only durable facts that will help next time: what the project is, where key scripts and instances live, conventions, how the main systems work, decisions and gotchas, and my preferences. It isn't a task log, so keep it short.
- **Updating it:** use `script_read` first so `old_string` matches; the section headers make good anchors. Remove facts that have become wrong.
- **When it disagrees with the place:** check the place with `script_read` or `inspect_instance`, then fix whichever side is wrong. If the place itself has a real problem, tell me.
- **Never store a guess as a fact:** don't record an unverified theory about why something broke. If a recorded fix doesn't make a problem go away, treat the recorded cause as wrong and diagnose again from scratch.
