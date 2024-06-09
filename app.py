import argparse


import os
import random
import string
from git import Repo
from github import Github
import re

# Define ANSI escape codes for colors
BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
RESET = "\033[0m"
def fmt_color(text, color):
    return f"{color}{text}{RESET}"
def print_color(text, color):
    print(fmt_color(text, color))

yaml_content = """
name: Dummy Action

on: [push]

jobs:
build:
    runs-on: ubuntu-latest
    steps:
    - name: Run dummy command
    run: echo dummy
"""


def local_repo(localpath):
    # Initialize the repository
    repo = Repo(localpath)
    assert not repo.bare
    # print git repo owner and name
    # Get the URL of the 'origin' remote
    origin_url = repo.remotes.origin.url

    # Extract owner and repo name from the URL
    pattern = r'github\.com[:/](.*?)/(.*?)(?:\.git)?$'
    match = re.search(pattern, origin_url)

    if match:
        owner = match.group(1)
        repo_name = match.group(2)
        print(fmt_color(f"Repository: ", GREEN) + fmt_color(f"{owner}/{repo_name}", CYAN))
        return (repo, owner, repo_name)
    else:
        print_color("Could not parse owner and repository name from the URL", RED)
        return None

def dump_action_yaml(action_file_path, yaml_content):
    os.makedirs(os.path.dirname(action_file_path), exist_ok=True)
    with open(action_file_path, "w") as f:
        f.write(yaml_content)

def create(args):
    print(f"Repo path: {args.path}")
    repo, owner, repo_name = local_repo(args.path)
    
    # Create and checkout the new branch
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    branch_name = "prefix-" + random_suffix
    new_branch = repo.create_head(branch_name)
    new_branch.checkout()
    print(fmt_color(f"Branch created: ", GREEN) + fmt_color(f"{branch_name}", CYAN))
    
    # dump YAML content into action file 
    action_file_path = os.path.join(args.path, ".github", "workflows", "dummy_action.yml")
    dump_action_yaml(args.path, yaml_content=yaml_content)
    print(fmt_color(f"Action file created: ", GREEN) + fmt_color(f"{action_file_path}", CYAN))

    # Stage and commit the changes
    repo.index.add([action_file_path])
    repo.index.commit("Add dummy GitHub action")

    # Create a pull request
    g = Github(args.gh_token)
    github_repo = g.get_repo(owner + "/" + repo_name)
    pr = github_repo.create_pull(
        title="Add dummy GitHub action",
        body="This PR adds a dummy GitHub action that echoes 'dummy'.",
        head=branch_name,
        base="main"  # or the default branch of your repo
    )

    print(fmt_color(f"Pull request created: ", GREEN) + fmt_color(f"{pr.html_url}", CYAN))


    

def main():
    parser = argparse.ArgumentParser(description='Fetch Info from Github repository environment variables')
    subparsers = parser.add_subparsers(dest='cmd', help='Help...')

    create_parser = subparsers.add_parser('create', help='Fetch data')
    create_parser.add_argument('--path','-p', type=str, help='Local Git Repo Path',default=None)
    create_parser.add_argument('--gh-token','-t', type=str, help='Github API Token',default=None)

    create_parser.set_defaults(func=create)

    options = parser.parse_args()
    options.func(options)

if __name__ == '__main__':
    main()