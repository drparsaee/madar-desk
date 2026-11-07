"""Fail-closed host-side Gantt batch preflight. This module NEVER writes data.

Caller must supply the full authoritative host state, server-authenticated
identity/grants and current revision while holding a CAS lock. Only unified
SQLite may eventually commit this candidate with its other side effects.
"""

from datetime import date, timedelta
import re


class GanttShiftError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _deny(code):
    raise GanttShiftError(code)


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        day = date.fromisoformat(value)
    except ValueError:
        return None
    return day if day.year >= 1 else None


def _shift(task, days):
    start, end = _day(task.get("plannedStart")), _day(task.get("plannedEnd"))
    if start is None or end is None or end < start:
        _deny("missing_plan")
    try:
        new_start = start + timedelta(days=days)
        new_end = end + timedelta(days=days)
    except (OverflowError, ValueError):
        _deny("date_range")
    return {"plannedStart": new_start.isoformat(), "plannedEnd": new_end.isoformat()}


def prepare_gantt_shift(state, request, *, role, projects, actual_revision):
    """Return an immutable-in-input candidate; storage integration is NOT implemented.

    projects=None denotes unrestricted trusted host grants, not a missing
    authorization check. Errors have generic codes and never expose private IDs.
    """
    if (not isinstance(state, dict) or type(state.get("tasks")) is not list or
            type(request) is not dict or
            set(request) != {"taskId", "days", "expectedRevision"} or
            type(request["taskId"]) is not str or not request["taskId"] or
            type(request["days"]) is not int or request["days"] == 0 or
            abs(request["days"]) > 3660 or
            type(request["expectedRevision"]) is not str or
            not request["expectedRevision"]):
        _deny("invalid_request")
    if role not in ("admin", "editor"):
        _deny("forbidden")
    if type(actual_revision) is not str or not actual_revision:
        _deny("invalid_state")
    if request["expectedRevision"] != actual_revision:
        _deny("stale_revision")
    if projects is not None and type(projects) is not list:
        _deny("forbidden")
    all_ids = {}
    for task in state["tasks"]:
        if (type(task) is not dict or type(task.get("id")) is not str or
                not task["id"] or task["id"] in all_ids):
            _deny("invalid_state")
        all_ids[task["id"]] = task
    source = all_ids.get(request["taskId"])
    if source is None or source.get("deleted") or source.get("archived"):
        _deny("unavailable_target")
    pid = source.get("projectId")
    if type(pid) is not str or not pid:
        _deny("invalid_state")
    if projects is not None and pid not in projects:
        _deny("forbidden")
    group = [t for t in state["tasks"]
             if t.get("projectId") == pid and not t.get("deleted") and
             not t.get("archived")]
    if len(group) > 20000:
        _deny("too_many")
    by_id = {task["id"]: task for task in group}
    children = {task["id"]: [] for task in group}
    indegree = {task["id"]: 0 for task in group}
    bounds = {}
    existing_conflict = False
    for task in group:
        start, end = _day(task.get("plannedStart")), _day(task.get("plannedEnd"))
        if start is None or end is None or end < start:
            _deny("missing_plan")
        deps = task.get("dependencies", [])
        if type(deps) is not list:
            _deny("invalid_dependency")
        bounds[task["id"]] = (start, end)
    for task in group:
        start = bounds[task["id"]][0]
        deps = task.get("dependencies", [])
        seen = set()
        for dep in deps:
            if type(dep) is not str or dep in seen or dep == task["id"]:
                _deny("invalid_dependency")
            seen.add(dep)
            parent = by_id.get(dep)
            if parent is None:
                _deny("outside_project")
            if start <= bounds[parent["id"]][1]:
                existing_conflict = True
            children[dep].append(task["id"])
            indegree[task["id"]] += 1
    queue = sorted(key for key in by_id if indegree[key] == 0)
    order = []
    cursor = 0
    while cursor < len(queue):
        key = queue[cursor]
        cursor += 1
        order.append(key)
        for successor in children[key]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    if len(order) != len(group):
        _deny("dependency_cycle")
    if existing_conflict:
        _deny("existing_conflict")
    changes = {source["id"]: _shift(source, request["days"])}
    for key in order:
        if key == source["id"]:
            continue
        task = by_id[key]
        deps = task.get("dependencies", [])
        if not any(parent in changes for parent in deps):
            continue
        required = _day(task["plannedStart"])
        for parent_id in deps:
            parent = changes.get(parent_id, by_id[parent_id])
            required = max(required, _day(parent["plannedEnd"]) + timedelta(days=1))
        delta = (required - _day(task["plannedStart"])).days
        if delta > 0:
            changes[key] = _shift(task, delta)
        if len(changes) > 500:
            _deny("too_many")
    source_start = _day(changes[source["id"]]["plannedStart"])
    for predecessor in source.get("dependencies", []):
        if source_start <= _day(by_id[predecessor]["plannedEnd"]):
            _deny("earlier_than_predecessor")
    # A hidden, archived or other-project successor invalidates the operation.
    for task in state["tasks"]:
        if task["id"] in by_id:
            continue
        deps = task.get("dependencies", [])
        if type(deps) is not list:
            _deny("invalid_dependency")
        if any(parent in changes for parent in deps):
            _deny("outside_project")
    updates = [{"id": key, **proposal} for key, proposal in changes.items()]
    return {
        "nextState": {**state, "tasks": [
            {**task, **changes[task["id"]]} if task["id"] in changes else task
            for task in state["tasks"]
        ]},
        "updates": updates,
        "changedCount": len(updates),
        "scope": "full_host",
    }
