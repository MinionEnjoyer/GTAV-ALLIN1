# Tools

Windows CLI tools used by the installer at install time to build the preview
texture DLC pack. Run `runtools.ps1` from the project root to fetch and build
all required tools automatically.

## Required Files

| File | Source | Purpose |
|------|--------|---------|
| `RpfPatcher/RpfPatcher.exe` | Built from the bundled CodeWalker.Core project | Builds `.ytd` dictionaries from BC3 DDS files, converts Gen9 resources, and manages RPF archives |
| `YTDToolio.exe` | Built from [ytdtool](https://github.com/kngrektor/ytdtool) source | Legacy diagnostic utility; its PNG encoder is not used because it corrupts scanlines on current Windows systems |
| `gtautil.exe` | [gtautil](https://github.com/indilo53/gtautil/releases) v2.2.7 | Creates `.rpf` archives, extracts/rebuilds `update.rpf` |

## Setup

From the project root, run:

```powershell
.\runtools.ps1
```

This downloads gtautil and builds RpfPatcher. It also retains YTDToolio for
legacy diagnostics, but preview generation uses Pillow plus RpfPatcher.

### Build Requirements (for YTDToolio)

- .NET 5.0+ SDK
- Visual Studio Build Tools (for native DirectXTex dependency)
- Git (for cloning the repo)
