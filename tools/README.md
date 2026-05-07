# Tools

Windows CLI tools used by the installer at install time to build the preview
texture DLC pack. Run `runtools.ps1` from the project root to fetch and build
all required tools automatically.

## Required Files

| File | Source | Purpose |
|------|--------|---------|
| `YTDToolio.exe` | Built from [ytdtool](https://github.com/kngrektor/ytdtool) source | Packs PNG folders into GTA V `.ytd` texture dictionaries |
| `gtautil.exe` | [gtautil](https://github.com/indilo53/gtautil/releases) v2.2.7 | Creates `.rpf` archives, extracts/rebuilds `update.rpf` |

## Setup

From the project root, run:

```powershell
.\runtools.ps1
```

This will download gtautil and clone + build YTDToolio from source.

### Build Requirements (for YTDToolio)

- .NET 5.0+ SDK
- Visual Studio Build Tools (for native DirectXTex dependency)
- Git (for cloning the repo)
