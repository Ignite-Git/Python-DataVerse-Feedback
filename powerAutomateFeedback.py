import os
import json
import urllib.request
import urllib.error

from dotenv import load_dotenv

load_dotenv()


def sendFeedbackData(feedback_data: dict) -> dict:

    flow_url = os.environ["POWER_AUTOMATE_FLOW_URL"]

    payload = json.dumps(feedback_data).encode("utf-8")

    request = urllib.request.Request(
        flow_url,
        data=payload,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:

            response_body = response.read().decode("utf-8")

            return {
                "success": True,
                "status_code": response.status,
                "message": response_body
            }

    except urllib.error.HTTPError as e:

        return {
            "success": False,
            "status_code": e.code,
            "message": e.read().decode("utf-8", errors="replace")
        }

    except urllib.error.URLError as e:

        return {
            "success": False,
            "message": str(e.reason)
        }