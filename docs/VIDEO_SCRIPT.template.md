# Video script: 60 s screen recording, Shi Hao speaks

Generated from `docs/VIDEO_SCRIPT.template.md` by `python -m analysis.fill_docs`. Read it aloud once
with a timer. It must be under 65 s.

Before recording: `streamlit run app/streamlit_app.py`, browser at least 1280 px wide, page scrolled to the top.

| time | say | screen |
|---|---|---|
| 0–13 s | "In June our robot policy scored 141 on our own benchmark and 89 on the hidden one. The benchmark never tested the far placements." | Page title and the AIC pull-quote. |
| 13–30 s | "GapHunter samples the deployment domain, runs the policy — here, one Astra wrote for a UR5e peg-in-hole — and maps where it breaks." | Click **Re-run coverage**. Show the progress bar. Then the heatmap and the dashed box. |
| 30–38 s | "Same harness, any policy: plug in a run_trial and it gets the same map." | The policy-comparison table. |
| 38–52 s | "Inside the box, {local_success}. Outside, {outside_success}. Here's the failure, and here's what Astra thought it was doing." | Point at the numbers. Play the failure clip. Open **What Astra was thinking**. |
| 52–60 s | "Four-nines reliability is the job. You can't get there on a benchmark that stops here." | Hover the dashed rectangle. Cut. |

Numbers on screen for reference: benchmark covers {coverage} of the deployment domain · deployment
success {deploy_success} (n={n_deploy}) · local n={n_local} · outside n={n_outside}.

## Re-run during recording

With real results loaded, **Re-run coverage** runs 10 trials on the MuJoCo sim in about 4 s, so record it live.
The caption under the button names the sim. If it ever says "fake", restart the app with `GAPHUNTER_SIM=mujoco`.
Fake-sim re-runs are never merged into real results.
