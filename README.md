# shorts-safe-zone

Check that on-screen text in a vertical short-form video stays out of the areas
where the platform player draws its own UI.

On YouTube Shorts (and similar players such as Reels and TikTok) the top bar,
the right-hand button column and the bottom block with the channel name, title
and music ticker sit on top of your video. A caption that looks fine in the
editor can end up hidden behind the "Subscribe" button once it is uploaded.
`shorts-safe-zone` samples frames from a finished video, reads every piece of
text with OCR, and fails the check if any text box overlaps one of those zones.

It is meant to run as a gate at the end of a render pipeline: JSON on stdout,
and an exit code your script can act on.

## What it checks

- Only vertical videos (height > width) of 180 seconds or less are treated as
  shorts. Anything else is reported as `NOT_APPLICABLE` (exit 0).
- Frames are sampled at 2 per second with ffmpeg.
- Text is read with the macOS Vision framework (accurate mode), in two passes
  (`ja-JP,en-US` and `ko-KR,en-US` by default, which also covers Latin text).
- Text with OCR confidence below 0.5 or fewer than 2 letters/digits is ignored.
- Any remaining text box that overlaps a UI zone by at least one pixel is a hit.
  All text counts, including text that was already burned into source footage.

Default zones on a 1080x1920 frame (x0, y0, x1, y1):

| zone   | rect                     | covered by                              |
|--------|--------------------------|-----------------------------------------|
| top    | `0, 0, 1080, 150`        | search / menu icons                     |
| bottom | `0, 1480, 1080, 1920`    | channel name, title, music ticker       |
| right  | `930, 1000, 1080, 1480`  | like / comment / share button column    |

For other resolutions each axis is scaled by its own ratio
(a 540x960 video gets a bottom zone of `0, 740, 540, 960`).

## Install

Requirements: macOS (for the Vision framework), Python 3.9+, `ffmpeg`/`ffprobe`
on your PATH, and the Xcode Command Line Tools (`swiftc`). No Python packages
and no API keys are needed.

```sh
brew install ffmpeg            # if you do not have it yet
xcode-select --install         # if swiftc is missing
pip install git+https://github.com/eiaimulyo-pixel/shorts-safe-zone
```

On first use a small Swift OCR helper that ships with the package is compiled
once and cached in `~/.cache/shorts-safe-zone` (override with
`SHORTS_SAFE_ZONE_CACHE`).

## Usage

```sh
shorts-safe-zone check final.mp4
echo $?    # 0 = PASS (or NOT_APPLICABLE), 1 = FAIL, 2 = UNMEASURED
```

Example output for a video with "Follow for part 2" near the bottom:

```json
{
  "tool": "shorts-safe-zone",
  "video": "final.mp4",
  "verdict": "FAIL",
  "reason": "1 distinct text(s) overlap UI zones in 4 detection(s)",
  "frames": 4,
  "text_read": 8,
  "hits": [
    {
      "time": 0.25,
      "text": "Follow for part 2",
      "confidence": 1.0,
      "box": { "x": 312, "y": 1592, "w": 464, "h": 72 },
      "zones": ["bottom"]
    }
  ]
}
```

(Shortened: the real report also lists the settings, the scaled zones, the
file's SHA-256, its size and duration.)

`time` is in seconds and `box` is in pixels of the video, origin at the
top-left corner.

### Options

```
shorts-safe-zone check VIDEO [--zones zones.json] [--fps 2] [--max-seconds 180]
                             [--min-confidence 0.5] [--min-chars 2]
                             [--langs "ja-JP,en-US;ko-KR,en-US"] [-o report.json]
```

### Check planned boxes before rendering

If your renderer knows where it will place text, you can check the boxes
without rendering anything:

```sh
shorts-safe-zone box 200,900,600,100 100,1500,400,80
# exit 1: the second box (x,y,w,h) overlaps the bottom zone
shorts-safe-zone box 100,750,200,50 --size 540x960
```

### Custom zones

Different apps and different layouts need different zones. Pass a JSON file:

```json
{
  "base_size": [1080, 1920],
  "zones": [
    { "name": "top",    "rect": [0, 0, 1080, 150] },
    { "name": "bottom", "rect": [0, 1480, 1080, 1920] },
    { "name": "right",  "rect": [930, 1000, 1080, 1480] }
  ]
}
```

`base_size` is the frame the rects are written for; they are scaled to each
video. A plain list of `[x0, y0, x1, y1]` rects also works.

```sh
shorts-safe-zone check final.mp4 --zones my-zones.json
```

## Exit codes

| code | verdict          | meaning                                                    |
|------|------------------|------------------------------------------------------------|
| 0    | `PASS`           | text was read and none of it touches a UI zone             |
| 0    | `NOT_APPLICABLE` | landscape or longer than `--max-seconds`; no shorts UI     |
| 1    | `FAIL`           | at least one text box overlaps a UI zone                   |
| 2    | `UNMEASURED`     | the check could not run: unreadable file, no frames, OCR error, missing tool, bad zones file |

`UNMEASURED` is deliberately not a pass. A check that did not run says nothing
about the video, so a pipeline should stop on it the same way it stops on
`FAIL`.

## Limitations

- **UI positions differ by app version; not a substitute for checking on a real
  phone.** The default zones are a conservative project baseline for YouTube
  Shorts on a 9:16 frame. Players change their layout, and phones with other
  aspect ratios crop or letterbox differently.
- OCR can miss text: very small, low-contrast, heavily stylised or fast-moving
  text, and text that only appears between two sampled frames (raise `--fps`
  to sample more densely). A `PASS` means "no text was found in the zones",
  not "there is no text in the zones".
- Only text is checked. Faces, logos and other important visuals behind the UI
  are not detected.
- macOS only, because it relies on the Vision framework.

## Tests

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The end-to-end tests build synthetic videos with ffmpeg `drawtext` (text in the
bottom zone must fail, centred text must pass, a 540x960 video checks zone
scaling, and broken input must come back as `UNMEASURED`). They are skipped on
systems without macOS and ffmpeg.

## License

MIT. See [LICENSE](LICENSE).

Built with Claude Code.
