from runFeedback import runFeedbackTracker
from powerAutomateFeedback import sendFeedbackData


def main():

    # Get feedback tracking results
    feedback_data = runFeedbackTracker()

    # Send results to Power Automate
    response = sendFeedbackData(feedback_data)

    if not response.get("success"):
        raise RuntimeError(
            f"Power Automate failed: {response.get('message')}"
        )

    return response


if __name__ == "__main__":
    result = main()
    print(result)