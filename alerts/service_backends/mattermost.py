import json
import requests

from django import forms
from django.template.defaultfilters import truncatechars, date as date_filter

from snappea.decorators import shared_task
from bugsink.app_settings import get_settings
from bugsink.transaction import immediate_atomic

from issues.models import Issue


class MattermostConfigForm(forms.Form):
    webhook_url = forms.URLField(required=True)

    def __init__(self, *args, **kwargs):
        config = kwargs.pop("config", None)

        super().__init__(*args, **kwargs)
        if config:
            self.fields["webhook_url"].initial = config.get("webhook_url", "")

    def get_config(self):
        return {
            "webhook_url": self.cleaned_data.get("webhook_url"),
        }


def _store_failure_info(service_config_id, exception, response=None):
    from alerts.models import MessagingServiceConfig

    with immediate_atomic(only_if_needed=True):
        try:
            config = MessagingServiceConfig.objects.get(id=service_config_id)

            # Mirror fields used by slack backend for consistency
            from django.utils import timezone
            config.last_failure_timestamp = timezone.now()
            config.last_failure_error_type = type(exception).__name__
            config.last_failure_error_message = str(exception)

            if response is not None:
                config.last_failure_status_code = response.status_code
                config.last_failure_response_text = response.text[:2000]
                try:
                    json.loads(response.text)
                    config.last_failure_is_json = True
                except (json.JSONDecodeError, ValueError):
                    config.last_failure_is_json = False
            else:
                config.last_failure_status_code = None
                config.last_failure_response_text = None
                config.last_failure_is_json = None

            config.save()
        except MessagingServiceConfig.DoesNotExist:
            pass


def _store_success_info(service_config_id):
    from alerts.models import MessagingServiceConfig

    with immediate_atomic(only_if_needed=True):
        try:
            config = MessagingServiceConfig.objects.get(id=service_config_id)
            config.clear_failure_status()
            config.save()
        except MessagingServiceConfig.DoesNotExist:
            pass


def _mm_text_header(text: str) -> str:
    return f"#### {text}"


def _color_for(level: str | None, alert_reason: str) -> str:
    if level:
        l = level.lower()
        if l in ("fatal", "error"):
            return "#E03E2D"  # red
        if l == "warning":
            return "#FFA500"  # orange
        if l == "info":
            return "#439FE0"  # blue
        if l == "debug":
            return "#666666"  # gray
    # fallback by reason
    if alert_reason == "REGRESSED":
        return "#FFA500"  # orange
    if alert_reason == "UNMUTED":
        return "#2ECC71"  # green
    return "#439FE0"  # NEW/other → blue


@shared_task
def mattermost_send_test_message(webhook_url, project_name, display_name, service_config_id):
    data = {
        "text": "Test message by Bugsink.",
        "attachments": [
            {
                "color": "#439FE0",
                "title": "TEST: Message backend check",
                "text": f"Project: **{project_name}**\nBackend: **{display_name}**",
            }
        ],
    }

    try:
        result = requests.post(
            webhook_url,
            data=json.dumps(data),
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        result.raise_for_status()
        _store_success_info(service_config_id)
    except requests.RequestException as e:
        response = getattr(e, 'response', None)
        _store_failure_info(service_config_id, e, response)
    except Exception as e:
        _store_failure_info(service_config_id, e)


@shared_task
def mattermost_send_alert(webhook_url, issue_id, state_description, alert_article, alert_reason, service_config_id, unmute_reason=None):
    issue = Issue.objects.get(id=issue_id)

    # Pull latest event for richer context (level, env, release, server)
    from events.models import Event
    last_event = (
        Event.objects.filter(issue_id=issue_id)
        .order_by('-digested_at')
        .first()
    )

    issue_url = get_settings().BASE_URL + issue.get_absolute_url()
    short_title = truncatechars(issue.title().replace("|", ""), 140)

    # Helpful, minimal, visual attachment
    level = last_event.level if last_event else None
    color = _color_for(level, alert_reason)

    # Brief location line if we have it
    location = None
    if issue.last_frame_filename:
        location = issue.last_frame_filename
    elif issue.last_frame_module:
        location = issue.last_frame_module
    if issue.last_frame_function:
        location = (location + f" in `{issue.last_frame_function}`") if location else f"`{issue.last_frame_function}`"

    fields = [
        {"title": "Project", "value": issue.project.name, "short": True},
    ]
    if last_event and last_event.environment:
        fields.append({"title": "Env", "value": last_event.environment, "short": True})
    if last_event and last_event.release:
        fields.append({"title": "Release", "value": last_event.release, "short": True})
    fields.append({"title": "Last Seen", "value": date_filter(issue.last_seen, 'j M Y H:i'), "short": True})

    text = location or ""
    if unmute_reason:
        text = (text + ("\n" if text else "")) + unmute_reason

    data = {
        "attachments": [
            {
                "color": color,
                "title": f"{alert_reason}: {short_title}",
                "title_link": issue_url,
                "text": text,
                "fields": fields,
            }
        ]
    }

    try:
        result = requests.post(
            webhook_url,
            data=json.dumps(data),
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        result.raise_for_status()
        _store_success_info(service_config_id)
    except requests.RequestException as e:
        response = getattr(e, 'response', None)
        _store_failure_info(service_config_id, e, response)
    except Exception as e:
        _store_failure_info(service_config_id, e)


class MattermostBackend:

    def __init__(self, service_config):
        self.service_config = service_config

    def get_form_class(self):
        # Reuse the same simple config as Slack (webhook_url only)
        from .slack import SlackConfigForm
        return SlackConfigForm

    def send_test_message(self):
        mattermost_send_test_message.delay(
            json.loads(self.service_config.config)["webhook_url"],
            self.service_config.project.name,
            self.service_config.display_name,
            self.service_config.id,
        )

    def send_alert(self, issue_id, state_description, alert_article, alert_reason, **kwargs):
        mattermost_send_alert.delay(
            json.loads(self.service_config.config)["webhook_url"],
            issue_id, state_description, alert_article, alert_reason, self.service_config.id, **kwargs)
