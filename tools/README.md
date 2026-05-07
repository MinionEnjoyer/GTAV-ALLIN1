# Tools

Windows CLI tools used by the installer at install time to build the preview
texture DLC pack. Place these executables in this directory.

## Required Files

| File | Source | License |
|------|--------|---------|
| `texconv.exe` | [DirectXTex](https://github.com/microsoft/DirectXTex/releases) | MIT |
| `YTDToolio.exe` | [ytdtool](https://github.com/kngrektor/ytdtool/releases) | GPL |
| `gtautil.exe` | [gtautil](https://github.com/indilo53/gtautil/releases) (v2.2.7) | MIT |

## What They Do

- **texconv.exe** converts PNG images to DXT1/DXT5 DDS format (GPU-compressed)
- **YTDToolio.exe** packs a folder of DDS files into a GTA V `.ytd` texture dictionary
- **gtautil.exe** creates `.rpf` archives and can extract/rebuild `update.rpf`

## Download Instructions

1. **texconv.exe**: Go to the DirectXTex releases page, download the latest
   `texconv.exe` standalone binary for x64.

2. **YTDToolio.exe**: Go to the ytdtool releases page, download the latest
   release and extract `YTDToolio.exe`.

3. **gtautil.exe**: Go to the gtautil releases page (v2.2.7), download and
   extract `gtautil.exe`.

Place all three in this `tools/` directory.
