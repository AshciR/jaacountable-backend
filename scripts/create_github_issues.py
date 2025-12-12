#!/usr/bin/env python3
"""
Generic script to create GitHub issues from a YAML definition file using GitHub REST API.

Usage:
    python scripts/create_github_issues.py issues.yaml

Environment Variables:
    GITHUB_TOKEN: GitHub Personal Access Token with 'repo' scope
    GITHUB_REPO: Repository in format 'owner/repo' (optional, can be in YAML)

YAML Format:
    repository: owner/repo  # Optional, can be set via GITHUB_REPO env var
    issues:
      - title: Issue Title
        body: |
          Issue description in markdown.
          Supports multi-line text.
        labels:
          - label1
          - label2
        assignees:  # Optional
          - username1
        milestone: 1  # Optional milestone number
"""

import os
import sys
import yaml
import requests
from typing import Any


def load_issues_from_yaml(yaml_file: str) -> dict[str, Any]:
    """Load issue definitions from YAML file."""
    with open(yaml_file, "r") as f:
        return yaml.safe_load(f)


def get_repo_labels(repo: str, token: str) -> set[str]:
    """Get all available labels in the repository."""
    url = f"https://api.github.com/repos/{repo}/labels"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        labels = response.json()
        return {label["name"] for label in labels}
    except requests.RequestException as e:
        print(f"Warning: Could not fetch repository labels: {e}")
        return set()


def create_issue(
    repo: str,
    token: str,
    title: str,
    body: str = "",
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    milestone: int | None = None,
) -> dict[str, Any]:
    """
    Create a GitHub issue using REST API.

    Args:
        repo: Repository in 'owner/repo' format
        token: GitHub Personal Access Token
        title: Issue title
        body: Issue body (markdown)
        labels: List of label names
        assignees: List of GitHub usernames
        milestone: Milestone number

    Returns:
        API response as dict

    Raises:
        requests.RequestException: If API request fails
    """
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    payload = {
        "title": title,
        "body": body,
    }

    if labels:
        payload["labels"] = labels
    if assignees:
        payload["assignees"] = assignees
    if milestone:
        payload["milestone"] = milestone

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


def create_github_issues(
    yaml_file: str,
    github_token: str | None = None,
    github_repo: str | None = None,
    dry_run: bool = False,
) -> None:
    """
    Create GitHub issues from YAML definition file.

    Args:
        yaml_file: Path to YAML file with issue definitions
        github_token: GitHub Personal Access Token (or from GITHUB_TOKEN env var)
        github_repo: Repository in 'owner/repo' format (or from GITHUB_REPO env var or YAML)
        dry_run: If True, print issues without creating them

    Raises:
        ValueError: If required environment variables are missing
        requests.RequestException: If GitHub API requests fail
    """
    # Load GitHub token
    token = github_token or os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError(
            "GitHub token is required. Set GITHUB_TOKEN environment variable or pass as argument."
        )

    # Load issue definitions
    print(f"Loading issues from: {yaml_file}")
    data = load_issues_from_yaml(yaml_file)

    # Determine repository
    repo_name = github_repo or os.getenv("GITHUB_REPO") or data.get("repository")
    if not repo_name:
        raise ValueError(
            "Repository is required. Set GITHUB_REPO environment variable, "
            "pass as argument, or specify in YAML file."
        )

    print(f"Target repository: {repo_name}")
    print(f"Dry run: {dry_run}")
    print("-" * 80)

    # Get available labels in repository
    if not dry_run:
        available_labels = get_repo_labels(repo_name, token)
        if available_labels:
            print(f"Repository has {len(available_labels)} labels")

    # Create issues
    issues_data = data.get("issues", [])
    print(f"Found {len(issues_data)} issues to create\n")

    created_count = 0
    skipped_count = 0

    for idx, issue_data in enumerate(issues_data, start=1):
        title = issue_data.get("title")
        body = issue_data.get("body", "")
        labels = issue_data.get("labels", [])
        assignees = issue_data.get("assignees", [])
        milestone_number = issue_data.get("milestone")

        if not title:
            print(f"⚠️  Issue {idx}: Skipping (no title)")
            skipped_count += 1
            continue

        print(f"\n{'='*80}")
        print(f"Issue {idx}: {title}")
        print(f"{'='*80}")
        print(f"Labels: {', '.join(labels) if labels else 'None'}")
        print(f"Assignees: {', '.join(assignees) if assignees else 'None'}")
        if milestone_number:
            print(f"Milestone: #{milestone_number}")
        print(f"\nBody preview (first 200 chars):")
        print(f"{body[:200]}...")

        # Validate labels (if not dry run)
        if not dry_run and available_labels:
            invalid_labels = [label for label in labels if label not in available_labels]
            if invalid_labels:
                print(f"\n⚠️  Warning: Labels not found in repository: {', '.join(invalid_labels)}")
                print(f"   These labels will be created automatically.")

        if dry_run:
            print(f"\n✓ [DRY RUN] Would create issue: {title}")
            created_count += 1
            continue

        # Create the issue
        try:
            issue = create_issue(
                repo=repo_name,
                token=token,
                title=title,
                body=body,
                labels=labels,
                assignees=assignees if assignees else None,
                milestone=milestone_number,
            )

            print(f"\n✓ Created issue #{issue['number']}: {issue['html_url']}")
            created_count += 1

        except requests.RequestException as e:
            print(f"\n✗ Failed to create issue: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"   Response: {e.response.text}")
            skipped_count += 1

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Total issues: {len(issues_data)}")
    print(f"Created: {created_count}")
    print(f"Skipped: {skipped_count}")

    if dry_run:
        print(f"\n💡 This was a dry run. Use --create to actually create the issues.")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Create GitHub issues from YAML definition file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (preview issues without creating)
  python scripts/create_github_issues.py github_issues.yaml

  # Create issues
  python scripts/create_github_issues.py github_issues.yaml --create

  # Specify repository explicitly
  python scripts/create_github_issues.py github_issues.yaml --repo owner/repo --create

Environment Variables:
  GITHUB_TOKEN: GitHub Personal Access Token with 'repo' scope (required)
  GITHUB_REPO: Repository in format 'owner/repo' (optional)

Creating a GitHub Token:
  1. Go to https://github.com/settings/tokens
  2. Click "Generate new token" (classic)
  3. Select scope: 'repo' (Full control of private repositories)
  4. Generate token and copy it
  5. Export as environment variable: export GITHUB_TOKEN=ghp_xxxxx
        """,
    )

    parser.add_argument(
        "yaml_file",
        help="Path to YAML file with issue definitions",
    )

    parser.add_argument(
        "--repo",
        help="GitHub repository in 'owner/repo' format (overrides GITHUB_REPO env var)",
    )

    parser.add_argument(
        "--token",
        help="GitHub Personal Access Token (overrides GITHUB_TOKEN env var)",
    )

    parser.add_argument(
        "--create",
        action="store_true",
        help="Actually create issues (default is dry run)",
    )

    args = parser.parse_args()

    try:
        create_github_issues(
            yaml_file=args.yaml_file,
            github_token=args.token,
            github_repo=args.repo,
            dry_run=not args.create,
        )
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
