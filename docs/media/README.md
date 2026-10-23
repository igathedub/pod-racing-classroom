# Public demo media

- `demo.png`: English projector view with the complete three-track final standings, shown in the application's native responsive layout.
- `demo.webm`: 22-second VP9 replay clip, 1440 × 1000, showing actual recorded final-race playback and the overall-result reveal.

Suggested image alt text: **English Pod Lab projector showing a recorded five-pod final and the overall standings across three final tracks, with synthetic pilot Nadja002 as classroom champion.**

These are captures of the real application at commit `804ac8804dff8b29d0e1ccc4364bd29d0b46fdf2`, not mockups or seeded API results. A separate cold-start Docker application accepted six synthetic submissions through its HTTP API, ran 18 qualification races and three final races, and retained 21 real replay archives. Student sources executed only inside restricted Docker sandbox children. Native Chromium displayed unchanged HTTP responses relayed from that isolated application; no host port was published.

All pilot aliases and source variations were created specifically for this demo. The deliberate invalid-command entry demonstrates disqualification. The individual last-race winner differs from the valid three-track overall champion. No teacher token, student claim token, private source, or production classroom data is included in the media.

The screenshot uses the real stacked projector layout so that all three final-time columns and the total are visible. The clip uses the wide projector layout and normal playback controls. The isolated application, its sandbox children, and its dedicated data volume were removed after capture, with absence verified. Existing release image tags were not rebuilt or changed.
