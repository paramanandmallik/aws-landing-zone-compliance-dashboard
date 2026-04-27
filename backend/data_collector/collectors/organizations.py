"""Collectors for AWS Organizations: accounts, OUs, and policies."""

import json
import logging

logger = logging.getLogger(__name__)

POLICY_TYPES = [
    "SERVICE_CONTROL_POLICY",
    "TAG_POLICY",
    "BACKUP_POLICY",
    "AISERVICES_OPT_OUT_POLICY",
]


def collect_accounts(session) -> list[dict]:
    """Paginate list_accounts and resolve each account's parent OU.

    Requirements: 1.1
    """
    try:
        client = session.client("organizations")
        paginator = client.get_paginator("list_accounts")
        accounts = []
        for page in paginator.paginate():
            for acct in page.get("Accounts", []):
                account = {
                    "id": acct["Id"],
                    "name": acct["Name"],
                    "email": acct["Email"],
                    "status": acct["Status"],
                    "arn": acct["Arn"],
                    "ou_id": "",
                    "ou_path": "",
                    "joined_timestamp": acct["JoinedTimestamp"].isoformat()
                    if hasattr(acct["JoinedTimestamp"], "isoformat")
                    else str(acct["JoinedTimestamp"]),
                }
                # Resolve parent OU
                try:
                    parents = client.list_parents(ChildId=acct["Id"])
                    if parents.get("Parents"):
                        account["ou_id"] = parents["Parents"][0]["Id"]
                except Exception:
                    logger.warning("Failed to resolve parent for account %s", acct["Id"])
                accounts.append(account)
        logger.info("Collected %d accounts", len(accounts))
        return accounts
    except Exception:
        logger.exception("Failed to collect accounts")
        return []


def _collect_ous_recursive(client, parent_id: str, parent_path: str) -> list[dict]:
    """Recursively collect OUs under a given parent."""
    ous = []
    paginator = client.get_paginator("list_organizational_units_for_parent")
    for page in paginator.paginate(ParentId=parent_id):
        for ou in page.get("OrganizationalUnits", []):
            ou_path = f"{parent_path}/{ou['Name']}"
            ous.append({
                "id": ou["Id"],
                "name": ou["Name"],
                "arn": ou["Arn"],
                "parent_ou_id": parent_id,
                "path": ou_path,
            })
            ous.extend(_collect_ous_recursive(client, ou["Id"], ou_path))
    return ous


def collect_ous(session) -> list[dict]:
    """Recursively collect all OUs starting from each root.

    Requirements: 1.1
    """
    try:
        client = session.client("organizations")
        roots_resp = client.list_roots()
        all_ous = []
        for root in roots_resp.get("Roots", []):
            root_id = root["Id"]
            root_name = root.get("Name", "Root")
            all_ous.append({
                "id": root_id,
                "name": root_name,
                "arn": root["Arn"],
                "parent_ou_id": None,
                "path": root_name,
            })
            all_ous.extend(_collect_ous_recursive(client, root_id, root_name))
        logger.info("Collected %d OUs (including roots)", len(all_ous))
        return all_ous
    except Exception:
        logger.exception("Failed to collect OUs")
        return []


def collect_policies(session) -> list[dict]:
    """Collect all policies (SCP, TAG, BACKUP, AISERVICES_OPT_OUT) with content and targets.

    Requirements: 1.2
    """
    policies = []
    try:
        client = session.client("organizations")
    except Exception:
        logger.exception("Failed to create Organizations client for policies")
        return []

    for policy_type in POLICY_TYPES:
        try:
            paginator = client.get_paginator("list_policies")
            for page in paginator.paginate(Filter=policy_type):
                for summary in page.get("Policies", []):
                    policy_id = summary["Id"]
                    policy = {
                        "id": policy_id,
                        "name": summary["Name"],
                        "arn": summary["Arn"],
                        "description": summary.get("Description", ""),
                        "type": summary["Type"],
                        "content": {},
                        "targets": [],
                    }
                    # Fetch full policy content
                    try:
                        desc = client.describe_policy(PolicyId=policy_id)
                        content_str = desc["Policy"]["Content"]
                        policy["content"] = json.loads(content_str) if isinstance(content_str, str) else content_str
                    except Exception:
                        logger.exception("Failed to describe policy %s", policy_id)

                    # Fetch attachment targets
                    try:
                        targets_paginator = client.get_paginator("list_targets_for_policy")
                        for tpage in targets_paginator.paginate(PolicyId=policy_id):
                            for target in tpage.get("Targets", []):
                                policy["targets"].append({
                                    "target_id": target["TargetId"],
                                    "target_type": target["Type"],
                                    "target_name": target.get("Name", ""),
                                })
                    except Exception:
                        logger.exception("Failed to list targets for policy %s", policy_id)

                    policies.append(policy)
        except Exception:
            logger.exception("Failed to collect policies of type %s", policy_type)

    logger.info("Collected %d policies", len(policies))
    return policies
