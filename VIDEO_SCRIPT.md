# Video script — 60 s screen recording, Shi Hao speaks

Numbers marked **TBD** are filled from `results/local.csv` / `results/deploy.csv` at 15:00.
Before recording: `streamlit run app/streamlit_app.py`, browser at 1280 px wide or more, page scrolled to the top.

| time | say | screen |
|---|---|---|
| 0–15 s | "In June our robot policy scored 141 on our own benchmark and 89 on the hidden one. The benchmark never tested the far placements." | Page title and the backstory line. |
| 15–35 s | "GapHunter samples the deployment domain, runs the policy — here, Astra driving a Franka — and maps where it breaks." | Click **Re-run coverage**. Show the progress bar. Then the heatmap and the dashed box. |
| 35–50 s | "Inside the box, **TBD**%. Outside, **TBD**%. Here's the failure, and here's what Astra thought it was doing." | Point at the tiles. Play the failure clip. Open **What Astra was thinking**. |
| 50–60 s | "Four-nines reliability is the job. You can't get there on a benchmark that stops here." | Hover the dashed rectangle. Cut. |

Word count: about 95 spoken words, which fits 60 s at a normal pace. Read it aloud once with a timer; it must be under 65 s.

## Re-run during recording

A real trial takes minutes, so 10 real trials will not finish inside 20 s. Two options:
1. Record the click and the progress bar starting, then cut to the finished page.
2. Start the app with `GAPHUNTER_FAKE_RERUN=1` so the button runs the fake sim. The narration must
   not then claim those 10 trials are Astra.
