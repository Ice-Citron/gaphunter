# Video script: 60 s screen recording, Shi Hao speaks

Fill the `{placeholders}` at 15:00 with `python -m analysis.fill_docs`, then read the script aloud once
with a timer. It must be under 65 s.

Before recording: `streamlit run app/streamlit_app.py`, browser at least 1280 px wide, page scrolled to the top.

| time | say | screen |
|---|---|---|
| 0–15 s | "In June our robot policy scored 141 on our own benchmark and 89 on the hidden one. The benchmark never tested the far placements." | Page title and the backstory line. |
| 15–35 s | "GapHunter samples the deployment domain, runs the policy — here, Astra driving a Franka — and maps where it breaks." | Click **Re-run coverage**. Show the progress bar. Then the heatmap and the dashed box. |
| 35–50 s | "Inside the box, {local_success}. Outside, {outside_success}. Here's the failure, and here's what Astra thought it was doing." | Point at the tiles. Play the failure clip. Open **What Astra was thinking**. |
| 50–60 s | "Four-nines reliability is the job. You can't get there on a benchmark that stops here." | Hover the dashed rectangle. Cut. |

Numbers on screen for reference: benchmark covers {coverage} of the deployment area · deployment
success {deploy_success} (n={n_deploy}) · local n={n_local} · outside n={n_outside}.

## Re-run during recording

A real trial takes minutes, so 10 real trials will not finish inside 20 s. Choose one:
1. Record the click and the progress bar starting, then cut to the finished page.
2. Start the app with `GAPHUNTER_FAKE_RERUN=1` so the button uses the fake sim. The narration must not
   then call those 10 trials Astra.
