from verify import (
    verify_log,
    verify_projection,
    verify_view_layer,
    verify_incremental_projection,
    verify_output_stability,
    verify_artifact_stability,
    verify_render_request_stability,
    verify_render_execution,
    verify_worker_isolation,
)


def verify_engine(log):
    try:
        events = log.get_events()
        verify_log(events)
        verify_projection()
        verify_view_layer()
        verify_incremental_projection()
        verify_output_stability()
        verify_artifact_stability()
        verify_render_request_stability()
        verify_render_execution()
        verify_worker_isolation()

        try:
            from observability.event_trace import log_event
            log_event("VERIFY_CHAIN_PASS")
        except Exception:
            pass

        return True

    except Exception as e:
        try:
            from observability.event_trace import log_event
            log_event("VERIFY_CHAIN_FAIL", metadata={"reason": str(e)})
        except Exception:
            pass
        raise
