# Video Knowledge reference

Video Knowledge accepts MP4, MOV and WebM files up to 50 MB. The first implementation uses the `hybrid_frames` profile: FFmpeg extracts ordered frames, and the explicitly configured `image_qa` model produces observations. Agent tools retrieve those observations alongside existing text Knowledge.

This profile does not call native video embeddings, use Metal for video inference, analyze clip audio, or recognize a person's identity. The embedding service on 8090 and Decision Maker on 8095 are unchanged.

## Configuration

`LOCAL_KNOWLEDGE_VIDEO_ENABLED` defaults to `false`. When enabled, readiness requires `ffmpeg`, `ffprobe` and a configured image QA model. The provider receives sampled JPEG frames. No external provider is selected automatically.

`KNOWLEDGE_VIDEO_FRAME_STRIDE` defaults to 30 decoded frames (allowed 1–300). `KNOWLEDGE_VIDEO_MAX_FRAMES` defaults to 24 (allowed 3–96). Sampling is by original decoded frame index, not assumed frame rate. Imports analyze at most three frames per vision request. Upload preview only decodes up to three frames; it does not run AI analysis.

`VIDEO_ATTACHMENT_STORAGE_DIR` defaults to `video_attachments` beside `OKF_STORAGE_DIR`. This directory must be writable, private and persistent for job recovery. Docker installs FFmpeg in the backend image. Enabling the flag requires a backend restart; installing the new code requires a rebuild.

## Time and coverage

Every observation retains its original zero-based decoded frame index. Media offsets are present only when source packet timestamps and decoded timestamps are usable. Unknown duration or timestamps do not prevent decoding a readable video. Responses then cite frame order; the UI displays one-based frame numbers.

Media offsets are positions within a clip, not CCTV clock times. The system does not derive wall-clock time from upload time, filename, guessed frame rate or frame count. Camera overlay clock recognition and user-supplied clock anchors are not implemented.

The processor samples a bounded prefix. Long clips may have unprocessed later events. Even when sampling reaches the end, short events between samples may be missed. Event descriptions require at least two ordered frames within an analysis batch. This profile cannot guarantee exhaustive event counts, establish absence, or verify every door crossing in a long CCTV recording.

## Storage and access

Curated video Knowledge follows existing team visibility. Original clips, frame images and generated observations have integrity hashes. Playback URLs expire and are signed for the authorized team, source and asset. The backend supports HTTP byte ranges. Generated video observations are read-only; importing the source again regenerates evidence.

Customer uploads use a separate HTTP endpoint and session grant issued by the WebSocket connection. Clients send only the completed attachment ID and question over WebSocket, never video bytes. Each access checks the session, current grant generation, API key, team and expiry. Resetting the conversation revokes old grants and cancels its clips; disconnecting removes access. Customer clips expire after one hour and the worker removes their files. Upload grants renew while the WebSocket remains connected.

Jobs use persisted states (`queued`, `processing`, `ready`, `failed`, `cancelled`, `expired`) and a 30-minute processing lease. A restarted worker reclaims expired leases, with at most three claims. Publication checks the active lease and expiry so cancelled jobs cannot publish. PostgreSQL serializes each session's upload quota of four active clips.

Automatic handoff settings are unchanged.

## Verification

Run backend contracts from `server/`:

```sh
.venv/bin/python -m pytest tests/test_knowledge_video.py tests/test_video_attachments.py tests/test_workflow_preview.py -q
```

Run frontend regressions from `frontend/`:

```sh
npm run test:regression
npx tsc --noEmit
```

The backend tests include real FFmpeg decoding, missing-time fallback, bounded processing, access isolation, signed ranged playback, source integrity, cancellation, lease recovery and conversation reset. Frontend regressions cover video import readiness, playback evidence, reference-only inquiry, stale responses and grant renewal. These checks do not establish CCTV detection recall or appliance diagnostic accuracy; those require representative labelled clips.

## System Information

The Settings monitor shows video model configuration, FFmpeg/FFprobe execution checks and the conversation-clip worker task's liveness. Model configuration is labelled `Configured`, not `Healthy`: refreshing this page does not call the model. Decoder checks run locally with bounded timeouts.

Queue counts cover unexpired customer conversation clips in the requested team, or the default team when no team is supplied. Curated Knowledge import jobs use the existing import progress UI and are not included in these counts. A missing or completed worker task is reported as unavailable; unreadable queue data is unknown rather than zero.

Some compatible vision endpoints return prose instead of the requested JSON. Video analysis first tries one structured multimodal request. If that response fails validation, it asks the same configured model to describe the ordered images and then structure only that description in a text-only request. Final evidence still requires every original frame ID exactly once and rejects invented event references. No other provider or model is selected automatically. This fallback can add two model requests per batch. The whole clip has a 25-minute processing deadline, including decoding and any fallback calls.
