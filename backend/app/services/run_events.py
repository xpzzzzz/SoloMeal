from ..models.agent import RunEvent


def record(db, run):
    # Call only while creating the run or holding its row lock.
    run.event_seq = (run.event_seq or 0) + 1
    db.add(
        RunEvent(
            run_id=run.id,
            user_id=run.user_id,
            seq=run.event_seq,
            payload={"status": run.status, "steps": run.steps, "event_seq": run.event_seq},
        )
    )
