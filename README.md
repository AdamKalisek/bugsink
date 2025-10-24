# Bugsink: Self-hosted Error Tracking

* [Error Tracking](https://www.bugsink.com/error-tracking/)
* [Built to self-host](https://www.bugsink.com/built-to-self-host/)
* [Sentry-SDK compatible](https://www.bugsink.com/connect-any-application/)
* [Scalable and reliable](https://www.bugsink.com/scalable-and-reliable/)

### Screenshot

![Screenshot](https://www.bugsink.com/static/images/JsonSchemaDefinitionException.5e02c1544273.png)


### Installation & docs

The **quickest way to evaluate Bugsink** is to spin up a throw-away instance using Docker:

```
docker pull bugsink/bugsink:latest

docker run \
  -e SECRET_KEY=PUT_AN_ACTUAL_RANDOM_SECRET_HERE_OF_AT_LEAST_50_CHARS \
  -e CREATE_SUPERUSER=admin:admin \
  -e PORT=8000 \
  -p 8000:8000 \
  bugsink/bugsink
```

Visit [http://localhost:8000/](http://localhost:8000/), where you'll see a login screen. The default username and password
are `admin`.

Now, you can [set up your first project](https://www.bugsink.com/docs/quickstart/) and start tracking errors.

[Detailed installation instructions](https://www.bugsink.com/docs/installation/) are on the Bugsink website.

[More information and documentation](https://www.bugsink.com/)

## Build Your Own Docker Image

You can build and run your own image (keeping the same env interface):

Build from source (simple):

```
docker build -t yourorg/bugsink:latest .
```

Run it (same env vars as the public image):

```
docker run \
  -e SECRET_KEY=PUT_AN_ACTUAL_RANDOM_SECRET_HERE_OF_AT_LEAST_50_CHARS \
  -e CREATE_SUPERUSER=admin:admin \
  -e PORT=8000 \
  -e ALERTS_GLOBAL_SLACK_WEBHOOK_URL=https://chat.apertia.ai/hooks/your-webhook \
  -e ALERTS_GLOBAL_MESSAGE_BACKEND=mattermost \
  -p 8000:8000 \
  yourorg/bugsink:latest
```

Alternatively, build from the wheel for parity with published images:

```
python -m pip install build
python -m build --wheel
docker build -f Dockerfile.fromwheel \
  --build-arg WHEEL_FILE=$(ls dist/*.whl | tail -n1 | xargs -n1 basename) \
  -t yourorg/bugsink:latest .
```

Notes:
- `SECRET_KEY` must be truly random and at least 50 chars.
- Optionally set `DATABASE_URL` (postgres/mysql) or mount a volume to `/data` for sqlite (default).
- Set `BASE_URL` and `ALLOWED_HOSTS` appropriately when deploying behind a proxy.
- `ALERTS_GLOBAL_SLACK_WEBHOOK_URL` (optional) sends all project alerts to a single Slack/Mattermost-compatible webhook in addition to per-project configs.
- `ALERTS_GLOBAL_MESSAGE_BACKEND` can be `mattermost` (default) or `slack` to control formatting for the global webhook.
