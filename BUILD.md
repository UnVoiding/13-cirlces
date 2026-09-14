# Building The Hell 4 on Windows 11

## Prerequisites

Install **Visual Studio Build Tools** with the following components:

| Component | Where to find it |
|---|---|
| Desktop development with C++ workload | Workloads tab |
| MSVC Build Tools for x64/x86 (Latest) | Included automatically |
| Windows 11 SDK (10.0.22621.0) | Optional → Desktop development with C++ |

No XP support, no v141, no CMake/vcpkg/testing tools needed.

---

## Steps

### 1. Run InitProject.bat

From the repo root in a terminal:

```
InitProject.bat
```

This creates two files if they don't already exist:
- `personal.props` — your local build settings
- `thehell4.vcxproj.user` — debugger settings

### 2. Edit personal.props

Open `personal.props` and set:

```xml
<GameFolder>C:\path\to\your\output\dir\</GameFolder>
<FxCopDir>C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x86</FxCopDir>

```

- **GameFolder** — where the built `TH4.exe` will be placed. Must end with a backslash `\`. The default `$(MSBuildProjectDirectory)\build\` outputs into a `build/` folder at the repo root — no changes needed unless you want a different location.
- **FxCopDir** — directory containing `fxc.exe` (the HLSL shader compiler). The path above is correct if you installed Windows 11 SDK 10.0.22621.0.

### 3. Build

#### Option A — From VS Code (recommended)

Press `Ctrl+Shift+B` — VS Code will invoke MSBuild using the project's `.sln` file.

> If no build task exists yet, open the Command Palette (`Ctrl+Shift+P`) → **Tasks: Configure Default Build Task** → **Create tasks.json from template** → **MSBuild**, then point it at `TheHell_4.sln`.

#### Option B — From a Developer Command Prompt

Open a **Developer Command Prompt for VS Build Tools**, navigate to the repo root and run:

```
& "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\MSBuild\Current\Bin\MSBuild.exe" TheHell_4.sln /p:Configuration=Release /p:Platform=Win32
```

Or simply use the provided script:
```
.\build.ps1
```

Use `Configuration=Debug` for a debug build.

---

## After Building

Copy these files into your `GameFolder` to run the game:

```
config.ini
diabdat.mpq
TH2data.mor
13cirlces.MPQ
THmusic.mor   (optional)
```

Then launch `TH4.exe` directly or via the VS debugger.

---

## 13cirlces.MPQ — the mod's own interface assets

`13cirlces.MPQ` holds graphics assets authored for the mod itself (currently
`X\other\ManaOvfl.trn`, `ManaOvf2.trn` and `ManaOvf3.trn`, the progressively darker tones
the mana globe is refilled in when a Master Caster's mana goes above his maximum — one per
full bar of overflow, so 100-200%, 200-300% and 300%+ of max). The game opens it next to
`diabdat.mpq`, at a higher priority than every other archive, so anything in it wins over
the stock data. The game still runs without it — features that need one of its assets just
fall back to their plain look.

The loose source files live under `res\13cirlces\`, laid out exactly as they sit inside the
archive. To repack it after changing one of them:

```
python tools\make_mpq.py res\13cirlces <GameFolder>\13cirlces.MPQ
```

The three `ManaOvfl*.trn` tables are all generated in one go from a game palette (any level
palette will do - entries 128..255, the only ones the panel graphics use, are the same in
all of them):

```
tools\build_mpq_tools.bat
tools\mpq_extract.exe <GameFolder>\TH4data.mor . Levels\TownData\Town.pal
python tools\make_mana_overflow_trn.py Town.pal res\13cirlces\X\other
```

Passing `make_mana_overflow_trn.py` a preview directory and one or more panel `.cel` files
after that additionally renders PNG previews of how each filling will look — one per
overflow bar and fill level. The panel `.cel`s come out of `TH4data.mor`
(`CtrlPan\front_panel_mana_black.cel`, `front_panel_mana_blue.cel`) and the empty globe
they are compared against out of `DIABDAT.MPQ` (`CtrlPan\P8Bulbs.CEL`).

How dark each tone is lives in the `TONES` table at the top of that script. Note that both
panels' globes are already very dark artwork (mean liquid luminance 17 and 9 out of 255),
so plain darkening has almost no headroom past the first tone; the deeper two therefore
also shift hue — cold blue at 200%+, red at 300%+ — which is what actually makes them tell
apart on screen.

---

## Troubleshooting

| Error | Fix |
|---|---|
| `Cannot find fxc.exe` | Check `FxCopDir` in `personal.props` points to a folder that contains `fxc.exe` |
| `personal.props not found` | Run `InitProject.bat` first |
| `GameFolder` errors | Make sure the path ends with a backslash `\` and the folder exists |
| `v143 toolset not found` | In VS Build Tools installer, ensure "MSVC Build Tools for x64/x86 (Latest)" is checked |
