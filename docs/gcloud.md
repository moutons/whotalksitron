# Google Cloud Setup

This document covers setting up the Gemini backend via Vertex AI — the recommended path for production use, since it uses your GCP billing account and supports the latest models.

## Prerequisites

- A Google Cloud project with billing enabled
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`) installed
- Application Default Credentials configured: `gcloud auth application-default login`

## Vertex AI vs AI Studio

whotalksitron supports two Gemini API endpoints:

| | AI Studio | Vertex AI |
|---|---|---|
| Auth | API key | ADC / service account |
| Billing | Free tier + prepayment | GCP billing account |
| Models | Stable Gemini models | All models including preview |
| Large file upload | Files API (built-in) | Requires GCS staging bucket |
| Recommended for | Quick testing | Production use |

Set `GOOGLE_GENAI_USE_VERTEXAI=1` (or `gemini.use_adc = true` in config) to use Vertex AI.

## Environment variables

The cleanest way to configure Vertex AI is with a `.envrc` file (via [direnv](https://direnv.net/)) or your shell profile:

```sh
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"
export GOOGLE_GENAI_USE_VERTEXAI=1
export GOOGLE_CLOUD_STORAGE_BUCKET="your-staging-bucket"

# API key (optional if using ADC — but required for the Vertex AI endpoint
# when not using a service account)
export GOOGLE_CLOUD_API_KEY="your-key"
```

## API key setup

Create a key at **APIs & Services → Credentials** in the Cloud Console.

Restrict the key to these APIs only — nothing else:

- `aiplatform.googleapis.com` (Vertex AI)
- `storage.googleapis.com` (Cloud Storage, for GCS staging)

Do not leave API keys unrestricted. An unrestricted key can authenticate against any Google API.

## GCS staging bucket

Vertex AI does not support the Files API. Audio files larger than 20 MB must be staged in a GCS bucket and passed as a `gs://` URI.

### Create the bucket

```sh
gcloud storage buckets create gs://YOUR-BUCKET-NAME \
  --project=YOUR-PROJECT \
  --location=US \
  --uniform-bucket-level-access
```

Use a name that includes your project ID to avoid collision (e.g. `whotalksitron-staging-your-project`).

### Harden the bucket

```sh
# Prevent the bucket from ever being made public, even accidentally
gcloud storage buckets update gs://YOUR-BUCKET-NAME --public-access-prevention

# Add a lifecycle rule to auto-delete staged files after 7 days
echo '{"rule":[{"action":{"type":"Delete"},"condition":{"age":7}}]}' \
  | gcloud storage buckets update gs://YOUR-BUCKET-NAME --lifecycle-file=/dev/stdin
```

### Verify

```sh
gcloud storage buckets describe gs://YOUR-BUCKET-NAME
```

Expected:

```
public_access_prevention: enforced
uniform_bucket_level_access: true
lifecycle_config:
  rule:
  - action:
      type: Delete
    condition:
      age: 7
```

### IAM

By default the bucket inherits project-level IAM — only project members have access. Do not grant `allUsers` or `allAuthenticatedUsers` bindings on this bucket.

The account running `whotalksitron` needs `roles/storage.objectAdmin` on the bucket (project Owner already has this).

## Models

Vertex AI model IDs use the same names as AI Studio. Current recommended models for transcription:

| Model | Notes |
|---|---|
| `gemini-2.5-flash` | Best balance of speed and quality (default) |
| `gemini-2.5-pro` | Higher quality, slower, higher cost |
| `gemini-3.1-flash-lite` | Fastest, lowest cost |
| `gemini-3.1-flash` | Fast, good quality |

Pass with `--model MODEL_ID` or set `gemini.model` in config.

## Verify your setup

```sh
whotalksitron config --show
```

Should show:

```
gemini.use_adc = True
gemini.project = 'your-project-id'
gemini.location = 'us-central1'
gemini.gcs_bucket = 'your-staging-bucket'
gemini.model = 'gemini-2.5-flash'
```

Then run a quick test:

```sh
whotalksitron transcribe short-clip.mp3 --backend gemini
```
