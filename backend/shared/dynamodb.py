"""DynamoDB serialize/deserialize helpers for single-table governance store."""

import json
import os
from dataclasses import asdict, fields
from typing import Type

import boto3
from boto3.dynamodb.conditions import Key

from backend.shared.models import (
    Account,
    ControlTowerControl,
    DeploymentRequest,
    Observation,
    OrganizationalUnit,
    ServiceControlPolicy,
)

TABLE_NAME = os.environ.get("GOVERNANCE_TABLE", "GovernanceStore")

_dynamodb = None


def _get_table():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(TABLE_NAME)


# --- PK/SK builders per entity type ---

_PK_SK_MAP = {
    OrganizationalUnit: lambda e: (f"OU#{e.id}", "META"),
    Account: lambda e: (f"ACCOUNT#{e.id}", "META"),
    ServiceControlPolicy: lambda e: (f"SCP#{e.id}", "META"),
    ControlTowerControl: lambda e: (f"CONTROL#{e.control_identifier}", f"OU#{e.ou_id}"),
    Observation: lambda e: (f"OBSERVATION#{e.id}", "META"),
    DeploymentRequest: lambda e: (f"DEPLOYMENT#{e.id}", "META"),
}

# GSI1 key builders (only for entities that use GSI1)
_GSI1_MAP = {
    Observation: lambda e: (
        f"OBS#SEVERITY#{e.severity}",
        e.created_at,
    ),
    DeploymentRequest: lambda e: (
        f"DEPLOY#STATUS#{e.status}",
        e.requested_at,
    ),
}


def serialize(entity) -> dict:
    """Convert a dataclass entity to a DynamoDB item with PK/SK composite keys."""
    entity_type = type(entity)
    if entity_type not in _PK_SK_MAP:
        raise ValueError(f"Unsupported entity type: {entity_type.__name__}")

    pk, sk = _PK_SK_MAP[entity_type](entity)
    item = {"PK": pk, "SK": sk, "entity_type": entity_type.__name__}

    data = asdict(entity)
    for key, value in data.items():
        if value is None:
            continue
        # Store dicts/lists as JSON strings for DynamoDB compatibility
        if isinstance(value, (dict, list)):
            item[key] = json.dumps(value)
        else:
            item[key] = value

    # Add GSI1 keys if applicable
    if entity_type in _GSI1_MAP:
        gsi1pk, gsi1sk = _GSI1_MAP[entity_type](entity)
        item["GSI1PK"] = gsi1pk
        item["GSI1SK"] = gsi1sk

    return item


def _is_json_field(field_type) -> bool:
    """Check if a field type requires JSON deserialization (dict or list types)."""
    type_str = str(field_type)
    return any(t in type_str for t in ("dict", "list["))


def deserialize(item: dict, entity_type: Type):
    """Reconstruct a dataclass from a DynamoDB item."""
    entity_fields = {f.name: f for f in fields(entity_type)}
    kwargs = {}

    for name, f in entity_fields.items():
        raw = item.get(name)
        if raw is None:
            kwargs[name] = None
            continue

        # Reconstruct dicts/lists from JSON strings
        if _is_json_field(f.type):
            kwargs[name] = json.loads(raw) if isinstance(raw, str) else raw
        else:
            kwargs[name] = raw

    return entity_type(**kwargs)


def build_ou_tree(flat_ous: list) -> dict:
    """Build OU hierarchy tree from a flat list of OrganizationalUnit objects or dicts.

    Returns a dict with root OU(s) containing nested 'children' lists.
    Each node is a dict with OU fields plus a 'children' key.
    """
    # Normalize to dicts
    nodes = {}
    for ou in flat_ous:
        data = asdict(ou) if hasattr(ou, "__dataclass_fields__") else dict(ou)
        data["children"] = []
        nodes[data["id"]] = data

    roots = []
    for node in nodes.values():
        parent_id = node.get("parent_ou_id")
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"].append(node)
        else:
            roots.append(node)

    return roots


# --- DynamoDB query helpers ---

def query_by_pk(pk: str, sk_prefix: str | None = None) -> list[dict]:
    """Query items by partition key, optionally filtering by SK prefix."""
    table = _get_table()
    key_condition = Key("PK").eq(pk)
    if sk_prefix:
        key_condition = key_condition & Key("SK").begins_with(sk_prefix)
    response = table.query(KeyConditionExpression=key_condition)
    return response.get("Items", [])


def query_gsi1(gsi1pk: str, sk_prefix: str | None = None) -> list[dict]:
    """Query GSI1 by GSI1PK, optionally filtering by GSI1SK prefix."""
    table = _get_table()
    key_condition = Key("GSI1PK").eq(gsi1pk)
    if sk_prefix:
        key_condition = key_condition & Key("GSI1SK").begins_with(sk_prefix)
    response = table.query(
        IndexName="GSI1",
        KeyConditionExpression=key_condition,
    )
    return response.get("Items", [])


def scan_by_pk_prefix(pk_prefix: str, sk_value: str | None = None) -> list[dict]:
    """Scan for items whose PK begins with the given prefix, optionally filtering by exact SK."""
    table = _get_table()
    from boto3.dynamodb.conditions import Attr

    filter_expr = Attr("PK").begins_with(pk_prefix)
    if sk_value:
        filter_expr = filter_expr & Attr("SK").eq(sk_value)

    items = []
    response = table.scan(FilterExpression=filter_expr)
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        response = table.scan(
            FilterExpression=filter_expr,
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))
    return items


def put_item(entity) -> None:
    """Serialize and put a single entity into DynamoDB."""
    table = _get_table()
    item = serialize(entity)
    table.put_item(Item=item)


def batch_write(entities: list) -> None:
    """Batch write multiple entities to DynamoDB (max 25 per batch)."""
    table = _get_table()
    with table.batch_writer() as batch:
        for entity in entities:
            item = serialize(entity)
            batch.put_item(Item=item)
