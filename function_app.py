import azure.functions as func
import logging

from main import main as run_feedback_process

app = func.FunctionApp()


@app.timer_trigger(
    schedule="%TIMER_SCHEDULE%",
    arg_name="myTimer",
    run_on_startup=False,
    use_monitor=True
)
def feedback_tracker(myTimer: func.TimerRequest) -> None:

    logging.info("Feedback tracker execution started.")

    if myTimer.past_due:
        logging.warning("The feedback tracker execution is past due.")

    try:
        response = run_feedback_process()

        logging.info("Feedback tracker completed.")
        logging.info("Power Automate response: %s", response)

    except Exception:
        logging.exception("Feedback tracker execution failed.")
        raise