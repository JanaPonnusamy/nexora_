from modules.sync import runtime_repository


def create_task(payload):
    return {
        "task_id": runtime_repository.create_task(
            payload["tenant_id"],
            payload["store_id"],
            payload.get("execution_type", "FULL"),
            payload.get("sync_mode", "FULL"),
            payload.get("total_tables", 0),
        ),
        "status": "PENDING",
    }


def get_pending_tasks(store_id):
    return runtime_repository.get_pending_tasks(store_id)


def start_task(task_id):
    return runtime_repository.start_task(task_id)


def complete_task(task_id):
    return runtime_repository.complete_task(task_id)


def fail_task(task_id, message):
    return runtime_repository.fail_task(task_id, message)


def get_configuration(task_id):
    return runtime_repository.get_configuration(task_id)


def upload_chunk(payload):
    return runtime_repository.upload_chunk(
        payload["execution_id"],
        payload["table_name"],
        payload["chunk_no"],
        payload.get("rows", []),
        total_rows=payload.get("total_rows"),
        sync_type=payload.get("sync_type"),
    )


def control_stores(store_ids, action):
    return runtime_repository.control_stores(store_ids, action)


def ack_chunk(chunk_execution_id):
    return runtime_repository.ack_chunk(chunk_execution_id)


def get_chunk_status(execution_id):
    return runtime_repository.get_chunk_status(execution_id)


def get_live_status():
    return runtime_repository.get_live_status()


def report_table_metrics(payload):
    return runtime_repository.report_table_metrics(
        payload["execution_id"],
        payload["table_name"],
        payload.get("sync_type"),
        payload.get("rows_examined", 0),
        payload.get("rows_changed", 0),
        payload.get("rows_uploaded", 0),
        payload.get("rows_skipped", 0),
        payload.get("source_total", 0),
    )


def get_table_statistics():
    return runtime_repository.get_table_statistics()


def agent_heartbeat(payload, register=False):
    return runtime_repository.agent_heartbeat(
        payload.get("tenant_id"),
        payload["store_id"],
        payload.get("agent_version"),
        payload.get("connection_type"),
        payload.get("ip_address"),
        register=register,
        install_path=payload.get("install_path"),
        hostname=payload.get("hostname"),
    )


def mark_stale_agents_offline(threshold_seconds=300):
    return runtime_repository.mark_stale_agents_offline(threshold_seconds)
