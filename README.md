# DXF Dogbone

Windows app that adds **dogbone corner reliefs** to SolidWorks sheet-metal DXF flat patterns. A round end mill cannot cut a sharp inside corner; a dogbone cuts a small circle through that corner so the tool can reach it. The original DXF is never modified. Export writes a new file.

## Download

You need **Windows** and **Python 3.11 or newer**.

1. Install Python from [python.org](https://www.python.org/downloads/). During setup, check **Add python.exe to PATH**.
2. Get the project, either way:
   - On this page, click **Code → Download ZIP**, unzip it, and open the folder.
   - Or, if you have Git: `git clone https://github.com/john-semple/dxf-dogbone.git`
3. Double-click **`run.bat`**.

The first launch creates a `.venv` folder and installs the one library the app needs (`ezdxf`). Later launches reuse that environment and open the window.

If a Microsoft Store window opens instead of the app, turn off the Store aliases: **Settings → Apps → Advanced app settings → App execution aliases**, and switch **python.exe** and **python3.exe** off. Then run `run.bat` again.

## Use

1. **Open a DXF** (SolidWorks flat pattern). You can also pass a path: `run.bat path\to\part.dxf`.
2. **Step 1 — Designate Fold Lines.** Mark bend lines if the flat pattern has them. Layers whose names contain `bend`, `fold`, or `centerline` are preselected. You can add or remove lines by clicking. On export they move to a `FOLD_LINES` layer and are trimmed or extended to the dogbone arcs.
3. **Step 2 — Dogbone.** Set the **tool diameter**. The default is **1/8 in** (3.175 mm). Quick picks are 1/16 in, 1/8 in, and 1/4 in. A trailing `"` on a typed value means inches. Click the **two edges** that meet at the corner. Two ghost dogbones appear. Click the one you want. Anything that will be removed is shown in red before you confirm. **Apply All** writes the queued corners.
4. **Step 3 — Trim.** Optional. Click a line near the end you want to trim or extend. It snaps to the nearest intersection.
5. **Export**. The suggested name is `<original>_dogbone.dxf`. Confirm the preview before the file is written.

Undo steps back through applied batches. Revert returns to the file as loaded.

Sample DXFs live in [`samples/`](samples/).

## What it expects

- Units are **millimeters** (`$INSUNITS` = 4).
- Geometry the tool edits is `LINE`, `ARC`, `CIRCLE`, `POINT`, and `MTEXT`.
- Polylines, splines, and ellipses are copied through unchanged, with a warning.
- Shallow, near-straight corners are refused instead of drawing a degenerate relief.
- Overlapping dogbones: the second one is skipped with a warning.

## Tests

From the project folder, after `run.bat` has created `.venv` once:

```bat
.venv\Scripts\python.exe -m pytest -q
```
