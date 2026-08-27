# CodeGraph AI screenshot guide

This directory is reserved for real captures of the running CodeGraph AI application. Do not add generated mockups, fabricated metrics, or screenshots containing credentials, API keys, environment files, private repository content, or other secrets.

Use a public repository and capture backend-derived values only. Prefer PNG at a 1440px or 1920px desktop viewport unless a different size is specified below.

## Required captures

### `codegraph-dashboard.png`

The primary README hero image.

- Repository workspace in dark theme.
- Public repository identity and immutable snapshot metadata visible.
- Pipeline completed.
- Live Visual Preview populated with actual graph/vector metrics.
- Graph Structure Preview populated with a real bounded Neo4j neighborhood.
- Pipeline, Artifacts, and Actions rail visible.
- Recommended viewport: `1920x1080` or `1440x900`.

### `repository-dashboard.png`

An alternate or cropped repository overview capture.

- Completed pipeline.
- Repository header, pipeline progress, activity, previews, and right rail visible.
- Use only real persisted counts and backend events.

### `pipeline-running.png`

- Capture while structural analysis or graph persistence is genuinely running.
- Show the running stage and Live Backend Activity together.
- Include real backend timestamps and event messages.
- Do not stage fake percentages, ETAs, durations, or counts.

### `graph-preview.png`

- Use a completed repository graph.
- Show real files, classes, functions, methods, and persisted relationships.
- Select a node so neighborhood highlighting or inspection details are visible.
- Keep the preview bounded; do not substitute a generated network diagram.

### `intelligence-evidence.png`

- Ask a question that returns an evidence-grounded answer.
- Show the response and Evidence Explorer together.
- Include a real public file path, symbol, line range, and source excerpt.
- Confirm that no source content contains secrets before capture.

### `system-status.png`

- Show the System workspace with Backend, MongoDB, and Neo4j healthy.
- Capture only after the frontend has refreshed live readiness data.

## Adding screenshots to the main README

After a required file exists, add its Markdown reference to the appropriate README section. The primary capture should use:

```markdown
![CodeGraph AI Repository Intelligence Dashboard](docs/assets/codegraph-dashboard.png)
```

Verify every image path on GitHub before merging.
